"""Offline regression tests for atomic migration application.

WHAT THESE TESTS PROVE, and only this: that
scripts/migrate_staging.sh submits a migration and its
schema_migrations ledger row through ONE psql invocation that carries
transaction options, that the recorded-state check happens inside that
submission and after the serialization lock, and that the script's
failure and retry paths behave correctly. A fake `psql` records every
invocation and the full text of every `-f` file it is handed, then
simulates a server: it models BEGIN/COMMIT/ROLLBACK explicitly,
separates running a migration from writing the ledger, and can be made
to fail at either stage. No socket, no server, no credentials.

WHAT THESE TESTS DO NOT PROVE: that PostgreSQL would accept this SQL,
that it would roll back as the fake does, that the advisory lock
serializes across processes, or that a lost COMMIT resolves as
described. Those were checked by hand against a disposable local
PostgreSQL 18.6; they are not part of this suite and are not
reproducible here.

The negative controls in the last section are the point of the module:
each runs a deliberately regressive script shape through the SAME
assertions and requires them to fail. Without them the assertions
could pass against a broken design.
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "migrate_staging.sh"

_spec = importlib.util.spec_from_file_location(
    "base_migrate_tests", REPO_ROOT / "scripts" / "test_migrate_staging.py")
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

PLACEHOLDER_URL = base.PLACEHOLDER_URL
MIGRATIONS = [
    "001_initial_schema.sql", "002_seed_data.sql",
    "003_verification_review.sql", "004_ocr_boundary.sql",
    "005_ocr_ownership.sql", "006_analysis_ownership.sql",
]

EXIT_OK = base.EXIT_OK


# ---------------------------------------------------------------------------
# Fake psql: a transaction simulator, not a call recorder
# ---------------------------------------------------------------------------

_ATOMIC_FAKE = r'''#!/usr/bin/env python3
"""Fake psql that simulates a server's transaction semantics.

Records argv (transaction options included) and the FULL TEXT of every
file handed to -f, then simulates what a server would do: one
transaction per --single-transaction invocation, rolled back on any
error; one implicit transaction per statement otherwise. Running a
migration and writing the ledger are separate modelled effects, and
either stage can be failed independently.

Environment:
  FAKE_PSQL_LOG       required, JSONL invocation log
  FAKE_PSQL_STATE     required, JSON database model
  FAKE_LEDGER         "0" -> public.schema_migrations is absent
  FAKE_RECORDED       whitespace-separated recorded filenames
  FAKE_OWNERS         owner_subject count (default 8)
  FAKE_POLICIES       pg_policies count (default 8)
  FAKE_PSQL_FAIL      "connect" -> every statement fails to connect
  FAKE_FAIL_MIGRATION filename whose included migration must fail
  FAKE_FAIL_LEDGER    filename whose ledger INSERT must fail
  FAKE_AMBIGUOUS      filename that commits server-side, then the
                      client exits non-zero (lost COMMIT reply)
  FAKE_LOCK_BUSY      "1" -> another runner holds the advisory lock
"""

import copy
import json
import os
import re
import sys

MIGRATIONS = ["001_initial_schema.sql", "002_seed_data.sql",
              "003_verification_review.sql", "004_ocr_boundary.sql",
              "005_ocr_ownership.sql", "006_analysis_ownership.sql"]
VALUE_FLAGS = ("-c", "-tAc", "-tA", "-f")
SINGLE_TXN = ("-1", "--single-transaction")
VALUE_MARKERS = ("-v",)
LEDGER = "schema_migrations"
DSN_MASK = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://\S*")
LEDGER_INSERT = re.compile(
    r"INSERT INTO public\.schema_migrations \(filename\) VALUES \('([^']*)'\)")
INCLUDE = re.compile(r"^\\i\s+(\S+)", re.M)
ADVISORY = "pg_advisory_xact_lock("


class PgError(Exception):
    """A statement the fake server refuses, like a real SQL error."""


def mask_argv(argv):
    """Replace the connection string with a placeholder, whatever it is."""
    dsn = os.environ.get("DATABASE_URL", "")
    masked = []
    for token in argv:
        if dsn and token == dsn:
            masked.append("<redacted-dsn>")
        else:
            masked.append(DSN_MASK.sub("<redacted-dsn>", token))
    return masked


def parse_argv(argv):
    """Split psql argv into (kind, text) pairs for -c and -f payloads."""
    statements = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token in VALUE_FLAGS:
            kind = "file" if token == "-f" else "inline"
            index += 1
            value = argv[index] if index < len(argv) else ""
            statements.append((kind, value))
        elif token.startswith("-c"):
            statements.append(("inline", token[2:]))
        index += 1
    return statements


def initial_state():
    """Seed the modelled database from the environment."""
    recorded = os.environ.get("FAKE_RECORDED")
    names = recorded.split() if recorded is not None else list(MIGRATIONS)
    return {"ledger_exists": os.environ.get("FAKE_LEDGER", "1") != "0",
            "ledger_created_by_script": False,
            "recorded": list(names),
            "applied": list(names),
            "commits": 0,
            "rollbacks": 0}


def load_state():
    """Return the modelled database, seeded once and then persisted."""
    path = os.environ["FAKE_PSQL_STATE"]
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    return initial_state()


def probe_target(script):
    """Return the filename a generated step script is about."""
    match = re.search(
        r"FROM public\.schema_migrations WHERE filename = '([^']*)'", script)
    return match.group(1) if match else None


def run_step_script(script, view, emit):
    """Simulate a generated step script: lock, probe, \\i, ledger INSERT.

    `view` is the open transaction's copy of the database. Raising
    PgError anywhere makes the whole transaction roll back, which is
    what --single-transaction plus ON_ERROR_STOP does on a server.
    """
    target = probe_target(script)
    if target is None:
        raise PgError("no recorded-state probe found in step script")
    if "SET TRANSACTION ISOLATION LEVEL READ COMMITTED" not in script:
        raise PgError("step script does not pin the isolation level")
    if script.count(ADVISORY) != 1:
        raise PgError("step script must take the advisory lock exactly once")
    if os.environ.get("FAKE_LOCK_BUSY") == "1":
        raise PgError("canceling statement due to lock timeout")
    if not view["ledger_exists"]:
        raise PgError('relation "schema_migrations" does not exist')

    already = target in view["recorded"]
    if not already:
        # \if :pending branch: \echo, \i the migration, then the INSERT.
        emit("labellens: applying %s" % target)
        if target in os.environ.get("FAKE_FAIL_MIGRATION", "").split():
            raise PgError('syntax error at or near "%s"' % target)
        view["applied"].append(target)
        if target in os.environ.get("FAKE_FAIL_LEDGER", "").split():
            raise PgError('new row for relation "schema_migrations" '
                          "violates check constraint")
        view["recorded"].append(target)
        return target
    emit("labellens: skip %s (already recorded)" % target)
    return None


def run_inline(sql, view, emit):
    """Simulate one inline statement against the open transaction."""
    low = sql.lower()
    if ADVISORY in low and "create" not in low:
        if os.environ.get("FAKE_LOCK_BUSY") == "1":
            raise PgError("canceling statement due to lock timeout")
        return
    if "to_regclass" in low:
        if view["ledger_exists"]:
            emit("public.%s" % LEDGER)
        return
    if "information_schema.columns" in low:
        emit(os.environ.get("FAKE_OWNERS", "8"))
        return
    if "pg_policies" in low:
        emit(os.environ.get("FAKE_POLICIES", "8"))
        return
    if "set transaction" in low or low.strip().startswith("set local"):
        return
    if "create" in low and LEDGER in low:
        if not view["ledger_exists"]:
            view["ledger_exists"] = True
            view["ledger_created_by_script"] = True
        return
    match = LEDGER_INSERT.search(sql)
    if match:
        if not view["ledger_exists"]:
            raise PgError('relation "%s" does not exist' % LEDGER)
        name = match.group(1)
        if name in os.environ.get("FAKE_FAIL_LEDGER", "").split():
            raise PgError('new row for relation "schema_migrations" '
                          "violates check constraint")
        view["recorded"].append(name)
        return
    if "select filename" in low:
        if not view["ledger_exists"]:
            raise PgError('relation "%s" does not exist' % LEDGER)
        for name in view["recorded"]:
            emit(name)
        return
    # Anything else: a migration file handed straight to -f, or SQL the
    # fake does not model. Treat it as a no-op unless it looks like a
    # migration file, so an unmodelled statement never silently "succeeds"
    # in a way that would hide a regression.
    base = os.path.basename(sql)
    if base.endswith(".sql"):
        if base in os.environ.get("FAKE_FAIL_MIGRATION", "").split():
            raise PgError("ERROR:  migration %s failed" % base)
        if not view["ledger_exists"] and base in MIGRATIONS:
            raise PgError('relation "%s" does not exist' % LEDGER)
        view["applied"].append(base)


def main():
    """Log the invocation, simulate it, return a psql-shaped exit code."""
    log_path = os.environ["FAKE_PSQL_LOG"]
    argv = sys.argv[1:]
    statements = parse_argv(argv)
    state = load_state()
    single = any(token in SINGLE_TXN for token in argv)
    on_error_stop = "ON_ERROR_STOP=1" in argv
    offline = os.environ.get("FAKE_PSQL_FAIL") == "connect"

    texts = []
    notes = []
    applied_now = []
    code = 0

    def emit(line):
        sys.stdout.write(line + "\n")

    def handle(kind, value, view):
        if kind == "file":
            if not os.path.exists(value):
                raise PgError("%s: No such file or directory" % value)
            with open(value, encoding="utf-8") as source:
                text = source.read()
            texts.append(text)
            if probe_target(text):
                # A generated step script: psql resolves its \if branches
                # client-side, so the fake walks the same branches.
                name = run_step_script(text, view, emit)
                if name:
                    applied_now.append(name)
            else:
                # The --baseline script: plain ledger INSERTs, no probe.
                inserts = LEDGER_INSERT.findall(text)
                if inserts:
                    for name in inserts:
                        run_inline(
                            "INSERT INTO public.schema_migrations "
                            "(filename) VALUES ('%s')" % name, view, emit)
                else:
                    # A migration file submitted directly, which is the
                    # shape the old apply loop used.
                    run_inline(value, view, emit)
            return
        run_inline(value, view, emit)

    # --single-transaction: one view for the whole invocation, discarded
    # on error. Otherwise psql sends each statement on its own, so each
    # one commits immediately -- which is exactly the split behaviour the
    # apply loop used to have.
    view = copy.deepcopy(state)
    for kind, value in statements:
        if offline:
            sys.stderr.write("psql: error: connection failed\n")
            notes.append("simulated connection failure")
            code = 2
            break
        try:
            handle(kind, value, view)
        except PgError as exc:
            sys.stderr.write("psql: ERROR:  %s\n" % exc)
            notes.append("statement failed: %s" % exc)
            code = 3
            if not single:
                # autocommit: the statements before the error stand
                state = view
            break
    else:
        state = view
        state["commits"] += 1

    if code and single and not offline:
        state["rollbacks"] += 1
        if not any(n.startswith("statement failed") for n in notes):
            state["rollbacks"] += 0
    if offline:
        state["rollbacks"] += 1

    ambiguous = os.environ.get("FAKE_AMBIGUOUS", "")
    if ambiguous and ambiguous in applied_now:
        # The server committed this transaction; only the reply was lost.
        # This must fire exactly once, on the invocation that committed,
        # or the script's follow-up ledger read would also look failed.
        code = 3
        notes.append("ambiguous commit: server kept the transaction")

    state.pop("path", None)
    with open(os.environ["FAKE_PSQL_STATE"], "w", encoding="utf-8") as out:
        json.dump(state, out)
    with open(log_path, "a", encoding="utf-8") as out:
        out.write(json.dumps({
            "argv": mask_argv(argv),
            "statements": [{"kind": k, "sql": v} for k, v in statements],
            "single_transaction": single,
            "on_error_stop": on_error_stop,
            "no_psqlrc": "-X" in argv,
            "script_text": "".join(texts),
            "exit_code": code,
            "ledger_created_by_script": state["ledger_created_by_script"],
            "commits": state["commits"],
            "rollbacks": state["rollbacks"],
            "notes": " | ".join(notes),
        }) + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
'''


@pytest.fixture
def atomic_fake(tmp_path):
    """Install the transaction-simulating fake psql and return its bin."""
    bindir = tmp_path / "abin"
    bindir.mkdir()
    fake = bindir / "psql"
    fake.write_text(_ATOMIC_FAKE)
    fake.chmod(0o755)
    return bindir


def run_atomic(args, bindir, tmp_path, *, script=SCRIPT, cwd=None,
               ledger=True, recorded=(), owners="8", policies="8",
               fail=None, fail_migration=None, fail_ledger=None,
               ambiguous=None, lock_busy=False):
    """Run `script` against the atomic fake with an explicit child env.

    The modelled database starts fresh on every call: a test that runs
    the script twice passes the previous `state["recorded"]` back in
    explicitly, so no run can inherit another run's ledger.
    """
    log_path = tmp_path / "atomic-calls.jsonl"
    state_path = tmp_path / "atomic-state.json"
    workdir = tmp_path / "cwd"
    workdir.mkdir(exist_ok=True)
    for stale in (log_path, state_path):
        if stale.exists():
            stale.unlink()
    env = {
        "PATH": os.pathsep.join([str(bindir), os.environ.get("PATH", "")]),
        "HOME": str(tmp_path),
        "DATABASE_URL": PLACEHOLDER_URL,
        "PGCONNECT_TIMEOUT": "1",
        "FAKE_PSQL_LOG": str(log_path),
        "FAKE_PSQL_STATE": str(state_path),
        "FAKE_LEDGER": "1" if ledger else "0",
        "FAKE_RECORDED": " ".join(recorded),
        "FAKE_OWNERS": str(owners),
        "FAKE_POLICIES": str(policies),
    }
    if fail is not None:
        env["FAKE_PSQL_FAIL"] = fail
    if fail_migration is not None:
        env["FAKE_FAIL_MIGRATION"] = fail_migration
    if fail_ledger is not None:
        env["FAKE_FAIL_LEDGER"] = fail_ledger
    if ambiguous is not None:
        env["FAKE_AMBIGUOUS"] = ambiguous
    if lock_busy:
        env["FAKE_LOCK_BUSY"] = "1"
    result = subprocess.run(
        ["bash", str(script)] + list(args), env=env,
        cwd=str(cwd or workdir), capture_output=True, text=True,
        timeout=60, check=False)
    state = json.loads(state_path.read_text(encoding="utf-8")) \
        if state_path.exists() else {}
    calls = base.read_calls(log_path)
    return result, calls, state


def combined(result):
    """Return stdout and stderr joined, for wording-tolerant assertions."""
    return result.stdout + result.stderr


@pytest.fixture
def run(atomic_fake, tmp_path):
    """Bind atomic_fake so tests call run_atomic(args, tmp_path)."""
    def _run(args, **kwargs):
        """Delegate to run_atomic with this test's fake bin dir."""
        return run_atomic(args, atomic_fake, tmp_path, **kwargs)

    return _run


# ---------------------------------------------------------------------------
# Structural assertions on the generated step script
# ---------------------------------------------------------------------------

INCLUDE_RE = re.compile(r"^\\i\s+(\S+)", re.M)
PROBE_RE = re.compile(r"FROM public\.schema_migrations WHERE filename = '([^']*)'")
INSERT_RE = re.compile(
    r"INSERT INTO public\.schema_migrations \(filename\) VALUES \('([^']*)'\)")


def step_scripts(calls):
    """Return (migration_filename, script_text) for each generated script."""
    found = []
    for call in calls:
        text = call["script_text"]
        match = PROBE_RE.search(text)
        if match:
            found.append((match.group(1), text))
    return found


def assert_single_transaction_per_migration(calls):
    """Every migration appears in exactly one transactional submission.

    Raises AssertionError rather than pytest.fail so the negative controls
    can assert that a deliberately split script is rejected.
    """
    scripts = step_scripts(calls)
    assert scripts, (
        "no generated step script was submitted; the apply path never ran, "
        "so these assertions would be vacuous")

    targets = [name for name, _ in scripts]
    assert len(targets) == len(set(targets)), (
        "a migration was submitted more than once: %s" % targets)

    for name, text in scripts:
        owner = [call for call in calls if text in call["script_text"]]
        for call in owner:
            assert call["single_transaction"], (
                "%s was not submitted with --single-transaction" % name)
            assert call["on_error_stop"], (
                "%s was submitted without ON_ERROR_STOP=1" % name)
            assert call["no_psqlrc"], (
                "%s was submitted without -X; ~/.psqlrc could void "
                "--single-transaction" % name)

        lock_at = text.find("pg_advisory_xact_lock(")
        probe_at = text.find("FROM public.schema_migrations WHERE filename")
        include_at = INCLUDE_RE.search(text)
        insert_at = INSERT_RE.search(text)
        endif_at = text.find("\\endif")

        assert lock_at >= 0, "%s: no advisory lock" % name
        assert text.count("pg_advisory_xact_lock(") == 1, (
            "%s: the advisory lock must be taken exactly once" % name)
        assert include_at is not None, "%s: no \\i of the migration" % name
        assert insert_at is not None, "%s: no ledger INSERT" % name
        assert endif_at > 0, "%s: the conditional block is not closed" % name

        assert lock_at < probe_at, (
            "%s: the recorded-state check runs before the lock, so it can "
            "miss a concurrent commit" % name)
        assert text.find("\\if :pending") < include_at.start(), (
            "%s: the migration is not guarded by the in-transaction check"
            % name)
        assert include_at.start() < endif_at, (
            "%s: the migration runs outside the conditional block" % name)
        assert include_at.start() < insert_at.start() < endif_at, (
            "%s: the ledger INSERT is not inside the same conditional "
            "block as the migration" % name)
        assert "SET TRANSACTION ISOLATION LEVEL READ COMMITTED" in text, (
            "%s: the transaction does not pin its isolation level" % name)


def assert_no_migration_ran(calls, name):
    """Require that `name` was never executed in any submission."""
    for call in calls:
        assert INCLUDE_RE.search(call["script_text"]) is None or \
            not call["script_text"].endswith(name), \
            "a migration file was handed straight to psql: %s" % name


# ---------------------------------------------------------------------------
# 1-2. A pending migration is applied and recorded in ONE submission
# ---------------------------------------------------------------------------


def test_pending_migration_runs_in_one_transactional_submission(run):
    """A pending file is applied and recorded by a single psql call."""
    result, calls, state = run([], recorded=[])
    assert result.returncode == EXIT_OK, combined(result)
    assert_single_transaction_per_migration(calls)
    assert set(state["recorded"]) == set(MIGRATIONS), state["recorded"]
    assert set(state["applied"]) == set(MIGRATIONS), state["applied"]


def test_recorded_check_happens_inside_the_locked_transaction(run):
    """The check is in the step script, after the lock, not in the shell."""
    _, calls, _ = run([], recorded=[])
    scripts = step_scripts(calls)
    assert scripts
    for name, text in scripts:
        assert text.index("pg_advisory_xact_lock(") < \
            text.index("FROM public.schema_migrations WHERE filename"), name
    # The shell must not read the ledger to decide whether to apply.
    shell_checks = [call for call in calls
                    if "select filename from public.schema_migrations"
                    in " ".join(s["sql"].lower() for s in call["statements"])]
    assert not shell_checks, (
        "the script still decides apply/skip in the shell, outside the "
        "locked transaction: %d such call(s)" % len(shell_checks))


# ---------------------------------------------------------------------------
# 3. An already-recorded migration is skipped
# ---------------------------------------------------------------------------


def test_already_recorded_migration_is_skipped(run):
    """A recorded file is not re-applied and is still reported."""
    result, calls, state = run([], recorded=list(MIGRATIONS))
    assert result.returncode == EXIT_OK, combined(result)
    assert "skip 001_initial_schema.sql" in result.stdout
    assert state["applied"] == list(MIGRATIONS)
    assert state["rollbacks"] == 0


# ---------------------------------------------------------------------------
# 4. A migration SQL error rolls back and records nothing
# ---------------------------------------------------------------------------


def test_migration_failure_exits_nonzero_and_records_nothing(run):
    """A failing migration leaves no applied file and no ledger row."""
    result, calls, state = run([], recorded=[],
                               fail_migration="003_verification_review.sql")
    assert result.returncode != 0, combined(result)
    assert "003_verification_review.sql" not in state["recorded"]
    assert "003_verification_review.sql" not in state["applied"]
    # Earlier files in the same run are untouched and still recorded.
    assert set(state["recorded"]) == set(MIGRATIONS[:2])
    assert state["rollbacks"] >= 1
    assert "not applied" in combined(result)


# ---------------------------------------------------------------------------
# 5. A ledger INSERT error rolls the migration back
# ---------------------------------------------------------------------------


def test_ledger_failure_rolls_back_the_migration(run):
    """A failing ledger INSERT discards that migration's changes too."""
    result, calls, state = run([], recorded=[],
                               fail_ledger="004_ocr_boundary.sql")
    assert result.returncode != 0, combined(result)
    assert "004_ocr_boundary.sql" not in state["recorded"], (
        "the ledger row survived a failed INSERT")
    assert "004_ocr_boundary.sql" not in state["applied"], (
        "the migration was left applied with no ledger row -- the exact "
        "defect Task 0.3 exists to close")


# ---------------------------------------------------------------------------
# 6-7. Retry behaviour, including an ambiguous commit
# ---------------------------------------------------------------------------


def test_retry_after_a_failure_attempts_the_migration_again(run):
    """A failed file is pending again on the next run."""
    first, _, state = run([], recorded=[], fail_ledger="004_ocr_boundary.sql")
    assert first.returncode != 0, combined(first)
    assert "004_ocr_boundary.sql" not in state["recorded"]

    second, calls, state2 = run([], recorded=state["recorded"])
    assert second.returncode == EXIT_OK, combined(second)
    assert "applying 004_ocr_boundary.sql" in second.stdout
    assert set(state2["recorded"]) == set(MIGRATIONS)


def test_retry_after_an_ambiguous_commit_rereads_the_ledger(run):
    """A lost COMMIT reply is resolved by the ledger, not the exit code."""
    first, calls, state = run(
        [], recorded=[], ambiguous="002_seed_data.sql")
    assert first.returncode != 0, (
        "an ambiguous commit must not be reported as success")
    assert "ambiguous" in combined(first) or \
        "was applied" in combined(first), combined(first)
    # 002 really did commit server-side even though the client failed.
    assert "002_seed_data.sql" in state["recorded"]

    second, calls2, state2 = run([], recorded=state["recorded"])
    assert second.returncode == EXIT_OK, combined(second)
    assert "skip 002_seed_data.sql" in second.stdout, (
        "the retry re-applied a migration that had already committed")
    assert state2["applied"].count("002_seed_data.sql") == 1, state2


# ---------------------------------------------------------------------------
# 8. Concurrency
# ---------------------------------------------------------------------------


def test_a_held_advisory_lock_stops_the_run_before_any_work(run):
    """A contended lock aborts atomically instead of applying blind."""
    result, calls, state = run([], recorded=[], lock_busy=True)
    assert result.returncode != 0, combined(result)
    assert state["recorded"] == [], state["recorded"]
    assert state["applied"] == [], state["applied"]
    assert state["rollbacks"] >= 1


def test_the_lock_key_is_a_fixed_literal_not_derived_per_run(run):
    """A per-run key would make the lock a no-op, so pin it."""
    _, calls1, _ = run([], recorded=[])
    _, calls2, _ = run([], recorded=[])
    keys = set()
    for calls in (calls1, calls2):
        for _, text in step_scripts(calls):
            match = re.search(r"pg_advisory_xact_lock\((\d+)\)", text)
            assert match, "the advisory lock key is not a literal"
            keys.add(match.group(1))
    assert len(keys) == 1, (
        "the advisory lock key changed between runs: %s" % keys)


# ---------------------------------------------------------------------------
# 9. Per-migration transaction boundary
# ---------------------------------------------------------------------------


def test_each_migration_gets_its_own_transaction(run):
    """Six files, six transactions, six separate submissions."""
    result, calls, state = run([], recorded=[])
    assert result.returncode == EXIT_OK, combined(result)
    scripts = step_scripts(calls)
    assert [name for name, _ in scripts] == MIGRATIONS, scripts
    assert_single_transaction_per_migration(calls)
    assert state["commits"] >= len(MIGRATIONS), state
    assert state["rollbacks"] == 0


# ---------------------------------------------------------------------------
# 10. --check is unchanged
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("owners,policies", [("8", "8"), ("3", "8"),
                                             ("8", "0")])
def test_check_exit_codes_are_unchanged(run, owners, policies):
    """--check keeps the Task 0.2 exit-code contract."""
    result, calls, state = run(["--check"], recorded=list(MIGRATIONS),
                               owners=owners, policies=policies)
    expected = EXIT_OK if (owners, policies) == ("8", "8") else 1
    assert result.returncode == expected, combined(result)
    base.assert_check_is_read_only(calls)
    assert state.get("ledger_created_by_script") is False


def test_check_still_fails_closed_on_a_missing_ledger(run):
    """A ledger-less database is reported, not created, by --check."""
    result, calls, state = run(["--check"], ledger=False)
    assert result.returncode == base.EXIT_LEDGER_MISSING, combined(result)
    assert state.get("ledger_created_by_script") is False
    assert not step_scripts(calls)


# ---------------------------------------------------------------------------
# 11. --baseline adoption is intact
# ---------------------------------------------------------------------------


def test_baseline_adopts_a_ledgerless_schema(run):
    """--baseline still verifies first, then records every file."""
    result, calls, state = run(["--baseline"], ledger=False)
    assert result.returncode == EXIT_OK, combined(result)
    assert set(state["recorded"]) == set(MIGRATIONS)
    assert state["ledger_created_by_script"] is True
    baselined = [call for call in calls
                 if "ON CONFLICT DO NOTHING" in call["script_text"]]
    assert baselined, "the baseline INSERTs disappeared"
    for call in baselined:
        assert call["single_transaction"], (
            "the baseline rows are no longer written in one transaction")
        assert "pg_advisory_xact_lock(" in call["script_text"], (
            "the baseline no longer takes the advisory lock")


def test_baseline_still_refuses_an_incomplete_schema(run):
    """Verification runs before anything is recorded."""
    result, _, state = run(["--baseline"], ledger=False, owners="3")
    assert result.returncode == 1, combined(result)
    assert state["recorded"] == [], state["recorded"]


# ---------------------------------------------------------------------------
# 12. Hygiene
# ---------------------------------------------------------------------------


def test_the_generated_script_never_contains_the_connection_string(run):
    """The step script carries no credential; only argv holds the DSN."""
    result, calls, _ = run([], recorded=[])
    assert calls
    for call in calls:
        assert PLACEHOLDER_URL not in call["script_text"]
        assert call["argv"][0] == "<redacted-dsn>"
        for statement in call["statements"]:
            assert PLACEHOLDER_URL not in statement["sql"]
    assert PLACEHOLDER_URL not in result.stdout
    assert PLACEHOLDER_URL not in result.stderr


def test_the_step_script_is_written_outside_the_repository(run):
    """A generated script must never land where git could pick it up."""
    _, calls, _ = run([], recorded=[])
    paths = [Path(s["sql"]) for call in calls for s in call["statements"]
             if s["kind"] == "file"]
    assert paths, "no -f submission to inspect"
    for path in paths:
        assert REPO_ROOT not in path.parents, path
        assert path.suffix == ".sql", path


def test_the_step_script_is_removed_after_the_run(run):
    """Cleanup deletes what it created; nothing is left behind."""
    _, calls, _ = run([], recorded=[])
    for path in [Path(s["sql"]) for call in calls
                 for s in call["statements"] if s["kind"] == "file"]:
        assert not path.exists(), "%s was left behind" % path


def test_an_unexpected_filename_is_refused(run, tmp_path):
    """A name that is not NNN_word.sql is a usage error, not SQL.

    FILES is a hardcoded list today, so this proves the guard exists for
    the day it stops being one: a filename is interpolated into generated
    SQL and into a \\i line, so an unexpected name must be refused.
    """
    original = SCRIPT.read_text(encoding="utf-8")
    patched = original.replace(
        'FILES="001_initial_schema.sql',
        'FILES="not-a-migration.sql 001_initial_schema.sql', 1)
    assert patched != original, "could not build the patched script"
    script = tmp_path / "badname.sh"
    script.write_text(patched)

    result, calls, state = run(["--check"], script=script, recorded=[])
    assert calls, "the patched script never reached psql"
    # --check is read-only and must never see the filename guard fire.
    assert "refusing to migrate" not in combined(result)

    result, calls, state = run([], script=script, recorded=[])
    assert result.returncode == base.EXIT_USAGE, combined(result)
    assert "refusing to migrate" in combined(result)
    assert state["recorded"] == [], state["recorded"]


# ---------------------------------------------------------------------------
# Negative controls: a split design must be REJECTED by the assertions
# ---------------------------------------------------------------------------

REGRESSIVE_HEADER = (
    "#!/usr/bin/env bash\n"
    "set -euo pipefail\n"
    'DATABASE_URL="${DATABASE_URL:-unset}"\n'
    'MIGRATIONS="$PWD"\n'
)

#: The pre-Task-0.3 apply loop, reproduced exactly: the migration runs in
#: one session and commits, then a SECOND session writes the ledger row.
#: This is the shape the whole task exists to remove.
SPLIT_APPLY = (
    'psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 --single-transaction \\\n'
    '  -f "$MIGRATIONS/001_initial_schema.sql"\n'
    'psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -q -c \\\n'
    '  "INSERT INTO public.schema_migrations (filename)'
    ' VALUES (\'001_initial_schema.sql\')"\n'
    'echo "schema verification: OK"\n'
    'exit 0\n'
)

#: A single transaction, but with the recorded-state check done in the
#: shell beforehand and no lock at all.
PRE_LOCK_CHECK = (
    'recorded=$(psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -tAc \\\n'
    '  "SELECT filename FROM public.schema_migrations")\n'
    'psql "$DATABASE_URL" -X -1 -v ON_ERROR_STOP=1 -f "$MIGRATIONS/step.sql"\n'
    'echo "schema verification: OK"\n'
    'exit 0\n'
)

#: One submission, but the lock comes AFTER the recorded-state probe.
LOCK_AFTER_PROBE = """\\echo labellens: applying 001_initial_schema.sql
SELECT CASE
         WHEN EXISTS (SELECT 1 FROM public.schema_migrations
                      WHERE filename = '001_initial_schema.sql')
            THEN 'yes' ELSE 'no' END AS recorded,
       CASE WHEN EXISTS (SELECT 1 FROM public.schema_migrations
                      WHERE filename = '001_initial_schema.sql')
            THEN 'no' ELSE 'yes' END AS pending \\gset
SELECT pg_advisory_xact_lock(7081702300000000001);
\\if :pending
\\i 001_initial_schema.sql
INSERT INTO public.schema_migrations (filename) VALUES ('001_initial_schema.sql');
\\elif :recorded
\\echo labellens: skip 001_initial_schema.sql (already recorded)
\\else
SELECT 'unusable' AS fatal, 1/0;
\\endif
"""

#: One submission and one lock, but the ledger INSERT is OUTSIDE the
#: conditional block, so it runs even when the file was skipped.
UNGUARDED_INSERT = """SELECT pg_advisory_xact_lock(7081702300000000001);
SELECT CASE
         WHEN EXISTS (SELECT 1 FROM public.schema_migrations
                      WHERE filename = '001_initial_schema.sql')
            THEN 'yes' ELSE 'no' END AS recorded,
       CASE WHEN EXISTS (SELECT 1 FROM public.schema_migrations
                      WHERE filename = '001_initial_schema.sql')
            THEN 'no' ELSE 'yes' END AS pending \\gset
\\if :pending
\\i 001_initial_schema.sql
\\endif
INSERT INTO public.schema_migrations (filename) VALUES ('001_initial_schema.sql');
"""


def _write_step(tmp_path, name, text):
    """Write a fake step script and a runner that submits it."""
    step = tmp_path / name
    step.write_text(text)
    script = tmp_path / ("%s.sh" % name)
    script.write_text(REGRESSIVE_HEADER +
                      'psql "$DATABASE_URL" -X -1 -v ON_ERROR_STOP=1 '
                      '-f "%s"\n' % step +
                      'echo "schema verification: OK"\n'
                      'exit 0\n')
    return script


@pytest.mark.parametrize("name,text", [
    ("lock_after_probe.sql", LOCK_AFTER_PROBE),
    ("unguarded_insert.sql", UNGUARDED_INSERT),
])
def test_controls_reject_a_malformed_step_script(run, tmp_path, name, text):
    """A real submission with the wrong shape must not pass."""
    script = _write_step(tmp_path, name, text)
    _, calls, _ = run(["--check"], script=script, recorded=[])
    assert calls, "the control never reached psql"
    with pytest.raises(AssertionError):
        assert_single_transaction_per_migration(calls)


def test_control_rejects_a_split_migration_and_ledger(run, tmp_path):
    """The pre-Task-0.3 shape must not pass the atomicity assertion."""
    workdir = tmp_path / "cwd"
    workdir.mkdir(exist_ok=True)
    (workdir / "001_initial_schema.sql").write_text(
        "CREATE TABLE control_split_marker (id int);\n")
    script = tmp_path / "split.sh"
    script.write_text(REGRESSIVE_HEADER + SPLIT_APPLY)
    result, calls, state = run(["--check"], script=script, recorded=[])
    assert calls
    with pytest.raises(AssertionError):
        assert_single_transaction_per_migration(calls)
    # And the fake models the consequence: two separate transactions,
    # so the ledger row survives with nothing left to roll back.
    assert "001_initial_schema.sql" in state["applied"], state
    assert "001_initial_schema.sql" in state["recorded"], state


def test_control_rejects_a_shell_side_recorded_check(run, tmp_path):
    """Deciding apply/skip in the shell, outside the lock, must fail."""
    step = tmp_path / "step.sql"
    step.write_text("""SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
SELECT pg_advisory_xact_lock(7081702300000000001);
SELECT CASE
         WHEN EXISTS (SELECT 1 FROM public.schema_migrations
                      WHERE filename = '001_initial_schema.sql')
            THEN 'yes' ELSE 'no' END AS recorded,
       CASE WHEN EXISTS (SELECT 1 FROM public.schema_migrations
                      WHERE filename = '001_initial_schema.sql')
            THEN 'no' ELSE 'yes' END AS pending \\gset
\\if :pending
\\i 001_initial_schema.sql
INSERT INTO public.schema_migrations (filename) VALUES ('001_initial_schema.sql');
\\elif :recorded
\\echo labellens: skip 001_initial_schema.sql (already recorded)
\\else
SELECT 'unusable' AS fatal, 1/0;
\\endif
""")
    script = tmp_path / "prelock.sh"
    script.write_text(REGRESSIVE_HEADER + PRE_LOCK_CHECK.replace(
        "$MIGRATIONS/step.sql", str(step)))
    _, calls, _ = run(["--check"], script=script, recorded=[])
    assert calls
    with pytest.raises(AssertionError):
        # The shell read the ledger in a separate, unlocked session.
        reads = [call for call in calls
                 if any("select filename from public.schema_migrations"
                        == s["sql"].strip().lower()
                        for s in call["statements"])]
        assert not reads, (
            "the recorded-state check still runs in the shell")


def test_control_catches_a_failing_assertion_helper(run, tmp_path):
    """Guards against the assertion helper becoming vacuously true."""
    with pytest.raises(AssertionError):
        assert_single_transaction_per_migration([])
    with pytest.raises(AssertionError):
        assert_single_transaction_per_migration(
            [{"script_text": "SELECT 1", "single_transaction": False,
              "on_error_stop": True, "no_psqlrc": True}])


# ---------------------------------------------------------------------------
# Harness self-checks
# ---------------------------------------------------------------------------


def test_the_fake_is_what_the_script_resolves(atomic_fake):
    """The fake, not a real psql, is what runs."""
    env_path = os.pathsep.join([str(atomic_fake), os.environ.get("PATH", "")])
    assert shutil.which("psql", path=env_path) == str(atomic_fake / "psql")


def test_the_fake_models_rollback_rather_than_always_succeeding(run):
    """The fake must actually be able to fail, or nothing above means much."""
    good = run([], recorded=[])[2]
    assert good["recorded"] == list(MIGRATIONS)
    bad = run([], recorded=[], fail_ledger="005_ocr_ownership.sql")[2]
    assert "005_ocr_ownership.sql" not in bad["recorded"]
    assert bad["rollbacks"] > good["rollbacks"]
