"""Offline regression tests for scripts/migrate_staging.sh --check.

WHAT THESE TESTS PROVE, and only this: the script's control flow and
the SQL text it hands to `psql`. A fake `psql` executable placed
first on PATH records every invocation and answers from an in-test
model of a staging database. No server, no socket, no credentials, no
network, no real database.

WHAT THESE TESTS DO NOT PROVE: that PostgreSQL would accept the SQL,
that any real schema matches the expectations, that RLS behaves, or
that the migration system is production-safe. They are a harness over a
stub, not a database integration suite.

The script is invoked as `bash <absolute path>`, and it resolves its
own ROOT from BASH_SOURCE, so these tests do not depend on the caller's
working directory.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "migrate_staging.sh"

# Not a URL and not a credential: no scheme, host or port, so it can
# never resolve anywhere. The script passes DATABASE_URL straight to
# psql and never parses it. The fake masks it out of its log; no test
# asserts on it and no test prints it.
PLACEHOLDER_URL = "offline-placeholder-not-a-connection-string"

SUCCESS_LINE = "schema verification: OK"

EXIT_OK = 0
EXIT_VERIFY_FAILED = 1
EXIT_USAGE = 2
EXIT_LEDGER_MISSING = 3
EXIT_PSQL_FAILED = 4


# ---------------------------------------------------------------------------
# Fake psql
# ---------------------------------------------------------------------------

_FAKE_PSQL = '''#!/usr/bin/env python3
"""Stand-in for psql. Records argv, answers from a small state file.

Environment contract:
  FAKE_PSQL_LOG    required, append-only JSONL invocation log
  FAKE_PSQL_STATE  required, JSON file holding the modelled database
  FAKE_LEDGER      "0" means public.schema_migrations does not exist
  FAKE_RECORDED    whitespace-separated filenames already recorded
  FAKE_OWNERS      owner_subject column count to report (default 8)
  FAKE_POLICIES    pg_policies row count to report (default 8)
  FAKE_PSQL_FAIL   "connect" makes every statement fail to connect

The connection string is masked out of the log. No socket is opened.
"""

import json
import os
import re
import sys

DSN_MASK = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://\\S*")
MIGRATIONS = ["001_initial_schema.sql", "002_seed_data.sql",
              "003_verification_review.sql", "004_ocr_boundary.sql",
              "005_ocr_ownership.sql", "006_analysis_ownership.sql"]
LEDGER = "schema_migrations"
VALUE_FLAGS = ("-c", "-tAc", "-tA", "-f")


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


def load_state():
    """Return the modelled database state, seeded from the environment."""
    path = os.environ["FAKE_PSQL_STATE"]
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            state = json.load(handle)
        state["path"] = path
        return state
    recorded = os.environ.get("FAKE_RECORDED")
    return {"path": path,
            "ledger_exists": os.environ.get("FAKE_LEDGER", "1") != "0",
            "ledger_created_by_script": False,
            "recorded": (recorded.split() if recorded is not None
                         else list(MIGRATIONS))}


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


def answer(sql, state, emit):
    """Answer one statement, mutating `state` only when it is a write."""
    low = sql.lower()
    if "to_regclass" in low:
        if state["ledger_exists"]:
            emit("public.%s" % LEDGER)
        return "ledger presence probe"
    if "information_schema.columns" in low:
        emit(os.environ.get("FAKE_OWNERS", "8"))
        return "owner column count"
    if "pg_policies" in low:
        emit(os.environ.get("FAKE_POLICIES", "8"))
        return "owner policy count"
    if LEDGER not in low:
        return "statement not modelled"
    if "create" in low:
        if not state["ledger_exists"]:
            state["ledger_exists"] = True
            state["ledger_created_by_script"] = True
            return "CREATE TABLE ran: ledger created"
        return "CREATE TABLE IF NOT EXISTS was a no-op"
    if "insert" in low:
        state["recorded"].append("row")
        return "INSERT ran: ledger row added"
    if not state["ledger_exists"]:
        raise LookupError('relation "%s" does not exist' % LEDGER)
    for name in state["recorded"]:
        emit(name)
    return "ledger listing"


def main():
    """Log the invocation, print modelled rows, return a psql exit code."""
    log_path = os.environ["FAKE_PSQL_LOG"]
    argv = sys.argv[1:]
    statements = parse_argv(argv)
    state = load_state()
    notes = []
    code = 0
    offline = os.environ.get("FAKE_PSQL_FAIL") == "connect"

    def emit(line):
        """Write one row of modelled query output to stdout."""
        sys.stdout.write(line + "\\n")

    for kind, value in statements:
        if offline:
            sys.stderr.write("psql: error: connection to server failed\\n")
            notes.append("simulated connection failure")
            code = 2
            continue
        if kind == "file":
            notes.append("migration file handed to psql: %s"
                         % os.path.basename(value))
            continue
        try:
            notes.append(answer(value, state, emit))
        except LookupError as exc:
            sys.stderr.write("psql: error: %s\\n" % exc)
            notes.append("relation missing")
            code = 1

    record = {key: val for key, val in state.items() if key != "path"}
    with open(state["path"], "w", encoding="utf-8") as handle:
        handle.write(json.dumps(record))
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "argv": mask_argv(argv),
            "statements": [{"kind": k, "sql": v} for k, v in statements],
            "exit_code": code,
            "ledger_created_by_script": state["ledger_created_by_script"],
            "notes": " | ".join(notes),
        }) + "\\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
'''


@pytest.fixture
def fake_psql(tmp_path):
    """Install the fake psql in a private bin dir and yield its directory."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "psql"
    fake.write_text(_FAKE_PSQL)
    fake.chmod(0o755)
    return bindir


# ---------------------------------------------------------------------------
# Read vs mutation classifier (fails closed)
# ---------------------------------------------------------------------------

#: Statements whose *only* permitted meaning is observation.
READ_ONLY_HEADS = frozenset({
    "select", "with", "table", "values", "explain", "show",
})

#: Any one of these words anywhere in a statement forces "mutate".
#: ``create`` subsumes CREATE TABLE / CREATE INDEX / CREATE OR REPLACE.
MUTATION_WORDS = frozenset({
    "insert", "update", "delete", "merge", "upsert",
    "create", "alter", "drop", "truncate", "grant", "revoke",
    "copy", "replace", "lock", "vacuum", "reindex", "refresh",
    "cluster", "reassign", "security", "import", "do", "call",
    "prepare", "execute", "deallocate",
    "begin", "commit", "rollback", "savepoint", "release",
})

_DOLLAR_QUOTE = re.compile(r"\$\$|\$[A-Za-z_]*\$")
_FIRST_WORD = re.compile(r"\s*([A-Za-z_]+)")
_WORDS = re.compile(r"[a-z_]+")


def split_statements(sql):
    """Split SQL into comment-free statements.

    Raises ValueError for anything the scanner cannot model (unterminated
    literals or block comments). Dollar quoting is rejected outright.
    """
    if _DOLLAR_QUOTE.search(sql):
        raise ValueError("dollar quoting is not modelled")
    parts = []
    buf = []
    index = 0
    size = len(sql)
    while index < size:
        char = sql[index]
        if sql.startswith("--", index):
            while index < size and sql[index] != "\n":
                index += 1
            continue
        if sql.startswith("/*", index):
            end = sql.find("*/", index + 2)
            if end < 0:
                raise ValueError("unterminated block comment")
            index = end + 2
            continue
        if char in "'\"":
            index += 1
            while index < size and sql[index] != char:
                if char == "'" and sql[index:index + 2] == "''":
                    index += 1
                index += 1
            if index >= size:
                raise ValueError("unterminated literal")
            index += 1
            buf.append(" ")
            continue
        if char == ";":
            parts.append("".join(buf))
            buf = []
            index += 1
            continue
        buf.append(char)
        index += 1
    parts.append("".join(buf))
    return [part for part in parts if part.strip()]


def classify_statement(sql):
    """Return "read" or "mutate" for one statement.

    Fails closed: an unparseable statement, an unexpected leading verb,
    or any mutation keyword anywhere all return "mutate".
    """
    try:
        parts = split_statements(sql)
    except ValueError:
        return "mutate"
    if not parts:
        return "read"
    for part in parts:
        head = _FIRST_WORD.match(part)
        if head is None or head.group(1).lower() not in READ_ONLY_HEADS:
            return "mutate"
        words = set(_WORDS.findall(part.lower()))
        if words & MUTATION_WORDS:
            return "mutate"
    return "read"


def assert_check_is_read_only(calls):
    """Assert every statement the script sent was observational.

    Raises AssertionError, not pytest.fail, so the negative controls can
    assert that this helper rejects a deliberately regressive script.
    """
    for call in calls:
        for statement in call["statements"]:
            assert statement["kind"] != "file", (
                "psql was asked to run a migration file: %s"
                % statement["sql"])
            verdict = classify_statement(statement["sql"])
            assert verdict == "read", (
                "non-read SQL sent during --check (%s): %s"
                % (verdict, " ".join(statement["sql"].split())[:120]))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def read_calls(log_path):
    """Return the fake psql invocation log as a list of dicts."""
    if not log_path.exists():
        return []
    return [json.loads(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def run_script(args, bindir, tmp_path, *, script=SCRIPT, cwd=None,
               ledger=True, recorded=None, owners="8", policies="8",
               fail=None):
    """Run `script` with the fake psql first on PATH.

    Returns (CompletedProcess, calls, final fake state). The child gets
    a minimal explicit environment so no ambient DATABASE_URL can leak
    in and no fake can survive into a later test.
    """
    log_path = tmp_path / "psql-calls.jsonl"
    state_path = tmp_path / "psql-state.json"
    workdir = tmp_path / "cwd"
    workdir.mkdir(exist_ok=True)
    env = {
        "PATH": os.pathsep.join([str(bindir),
                                 os.environ.get("PATH", "")]),
        "HOME": str(tmp_path),
        "DATABASE_URL": PLACEHOLDER_URL,
        "PGCONNECT_TIMEOUT": "1",
        "FAKE_PSQL_LOG": str(log_path),
        "FAKE_PSQL_STATE": str(state_path),
        "FAKE_LEDGER": "1" if ledger else "0",
        "FAKE_OWNERS": str(owners),
        "FAKE_POLICIES": str(policies),
    }
    if recorded is not None:
        env["FAKE_RECORDED"] = " ".join(recorded)
    if fail is not None:
        env["FAKE_PSQL_FAIL"] = fail
    result = subprocess.run(
        ["bash", str(script)] + list(args),
        env=env, cwd=str(cwd or workdir), capture_output=True, text=True,
        timeout=60, check=False)
    state = json.loads(state_path.read_text(encoding="utf-8")) \
        if state_path.exists() else {}
    return result, read_calls(log_path), state


def combined(result):
    """Return stdout and stderr joined, for wording-tolerant assertions."""
    return result.stdout + result.stderr


@pytest.fixture
def run(fake_psql, tmp_path):
    """Bind fake_psql so tests can call run_script(args, tmp_path)."""
    def _run(args, **kwargs):
        """Delegate to run_script with this test's fake bin dir."""
        return run_script(args, fake_psql, tmp_path, **kwargs)

    return _run


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


def test_check_succeeds_when_ledger_and_schema_are_ready(run):
    """--check exits 0 and says so when the ledger exists and verifies."""
    result, calls, state = run(["--check"])
    assert result.returncode == EXIT_OK, combined(result)
    assert SUCCESS_LINE in result.stdout
    assert "001_initial_schema.sql" in result.stdout
    assert calls, "fake psql was never invoked; the test would be vacuous"
    assert state.get("ledger_created_by_script") is False


# ---------------------------------------------------------------------------
# 2. Missing ledger
# ---------------------------------------------------------------------------


def test_missing_ledger_fails_without_creating_it(run):
    """An absent ledger is reported and never created by --check."""
    result, calls, state = run(["--check"], ledger=False)
    assert result.returncode == EXIT_LEDGER_MISSING, combined(result)
    assert SUCCESS_LINE not in combined(result)
    haystack = combined(result).lower()
    hints = ("schema_migrations", "ledger", "absent", "missing",
             "does not exist")
    assert any(hint in haystack for hint in hints), combined(result)
    assert state.get("ledger_created_by_script") is False, (
        "the script created the migration ledger during --check")
    assert_check_is_read_only(calls)


# ---------------------------------------------------------------------------
# 3. Verification failure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("owners,policies", [
    ("3", "8"), ("8", "0"), ("0", "0"), ("9", "8"),
])
def test_check_fails_when_schema_verification_fails(run, owners, policies):
    """--check exits 1 when either expected count is wrong."""
    result, _, _ = run(["--check"], owners=owners, policies=policies)
    assert result.returncode == EXIT_VERIFY_FAILED, combined(result)
    assert SUCCESS_LINE not in combined(result)


# ---------------------------------------------------------------------------
# 4. psql failure
# ---------------------------------------------------------------------------


def test_psql_connection_failure_is_not_success(run):
    """A psql failure exits 4 and prints no success line."""
    result, calls, _ = run(["--check"], fail="connect")
    assert result.returncode == EXIT_PSQL_FAILED, combined(result)
    assert SUCCESS_LINE not in combined(result)
    assert calls, "fake psql was never invoked"


# ---------------------------------------------------------------------------
# 5 and 6. Argument rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("args", [
    ["--frobnicate"],
    ["--dry-run"],
    ["--CHECK"],
    [""],
    [" ", ""],
])
def test_bad_arguments_are_rejected_before_any_connection(run, args):
    """Unknown flags and an empty argument are usage errors (exit 2)."""
    result, calls, _ = run(args)
    assert result.returncode == EXIT_USAGE, combined(result)
    assert "usage" in combined(result).lower()
    assert calls == [], "database was contacted before argument validation"


@pytest.mark.parametrize("args", [
    ["--check", "--baseline"],
    ["--baseline", "--check"],
    ["apply", "--check"],
    ["--check", "extra"],
    ["--baseline", "extra"],
])
def test_extra_arguments_are_rejected(run, args):
    """More than one argument is a usage error, never a mode choice."""
    result, calls, _ = run(args)
    assert result.returncode == EXIT_USAGE, combined(result)
    assert calls == [], "extra arguments silently selected a mode"


# ---------------------------------------------------------------------------
# 7. Read-only guarantee for --check
# ---------------------------------------------------------------------------


def test_check_emits_only_reads(run):
    """Every statement issued under --check classifies as a read."""
    _, calls, state = run(["--check"])
    assert calls
    assert_check_is_read_only(calls)
    assert state.get("ledger_created_by_script") is False


def test_check_emits_no_ledger_ddl_at_all(run):
    """No CREATE TABLE of any kind is issued under --check."""
    _, calls, _ = run(["--check"])
    joined = " ".join(
        statement["sql"].lower() for call in calls
        for statement in call["statements"])
    assert "create table" not in joined
    assert "schema_migrations" not in joined or "select" in joined


def test_check_runs_no_migration_file_from_any_cwd(run, tmp_path):
    """The same guarantees hold when invoked from / and from the repo."""
    for cwd in (Path("/"), REPO_ROOT, tmp_path):
        _, calls, _ = run(["--check"], cwd=cwd)
        assert calls, "fake psql was never invoked from %s" % cwd
        assert_check_is_read_only(calls)


# ---------------------------------------------------------------------------
# 8. No success message after a failure
# ---------------------------------------------------------------------------


def test_no_success_message_after_a_failed_verification(run):
    """A short schema never yields the OK line."""
    result, _, _ = run(["--check"], owners="0", policies="0")
    assert SUCCESS_LINE not in combined(result)


def test_no_success_message_after_a_missing_ledger(run):
    """A missing ledger never yields the OK line."""
    result, _, _ = run(["--check"], ledger=False)
    assert SUCCESS_LINE not in combined(result)


# ---------------------------------------------------------------------------
# 9. Negative controls
# ---------------------------------------------------------------------------


MUTATING_SQL = [
    "CREATE TABLE IF NOT EXISTS public.schema_migrations (f TEXT)",
    "create table if not exists t (i int)",
    "INSERT INTO public.schema_migrations (filename) VALUES ('a')",
    "insert into t values (1)",
    "UPDATE public.schema_migrations SET applied_at = NOW()",
    "DELETE FROM public.schema_migrations",
    "ALTER TABLE ocr_runs ADD COLUMN x int",
    "DROP TABLE ocr_runs",
    "TRUNCATE ocr_runs",
    "COPY ocr_runs FROM '/etc/passwd'",
    "GRANT SELECT ON ocr_runs TO anon",
    "REVOKE SELECT ON ocr_runs FROM anon",
    "SELECT count(*) FROM ocr_runs FOR UPDATE",
    "WITH x AS (DELETE FROM ocr_runs RETURNING *) SELECT * FROM x",
    "SELECT 1; DROP TABLE ocr_runs",
    "SELECT 1; CREATE TABLE t (i int)",
    "VACUUM ocr_runs",
    "LOCK TABLE ocr_runs IN ACCESS EXCLUSIVE MODE",
    "CALL pg_reload_conf()",
    "-- a helpful comment\nCREATE TABLE t (i int)",
    "SELECT 'unterminated",
    "/* unterminated",
    "VACUUM",
]


@pytest.mark.parametrize("sql", MUTATING_SQL)
def test_classifier_rejects_mutation(sql):
    """Anything that could write, or cannot be parsed, is a mutation."""
    assert classify_statement(sql) == "mutate"


READ_ONLY_SQL = [
    "SELECT filename FROM public.schema_migrations",
    "SELECT to_regclass('public.schema_migrations')",
    "\nSELECT count(*) FROM information_schema.columns\n"
    "WHERE table_name IN ('ocr_runs')\n"
    "  AND column_name = 'owner_subject';",
    "SELECT count(*) FROM pg_policies WHERE tablename IN ('ocr_runs');",
    "WITH recent AS (SELECT filename FROM public.schema_migrations) "
    "SELECT count(*) FROM recent",
    "-- leading comment\nSELECT 1",
    "/* comment */ SELECT 1 FROM ocr_runs WHERE a = 'DROP TABLE x'",
    "SELECT 'unterminated-looking ; DROP TABLE x' AS literal_text",
]


@pytest.mark.parametrize("sql", READ_ONLY_SQL)
def test_classifier_accepts_observation(sql):
    """The reads the script actually sends stay classified as reads."""
    assert classify_statement(sql) == "read"


REGRESSIVE_HEADER = (
    "#!/usr/bin/env bash\n"
    "set -euo pipefail\n"
    'DATABASE_URL="${DATABASE_URL:-unset}"\n'
    'MIGRATIONS="$PWD"\n'
)

REGRESSIVE_SCRIPTS = {
    "recreates": (
        'psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -c \\\n'
        '  "CREATE TABLE IF NOT EXISTS public.schema_migrations (f TEXT)"\n'
        'psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -tAc \\\n'
        '  "SELECT to_regclass(\'public.schema_migrations\')"\n'
        'echo "schema verification: OK"\n'
        'exit 0\n'
    ),
    "inserts_ledger_row": (
        'psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -c \\\n'
        '  "INSERT INTO public.schema_migrations (filename)'
        ' VALUES (\'a\')"\n'
        'echo "schema verification: OK"\n'
        'exit 0\n'
    ),
    "runs_migration_file": (
        'psql "$DATABASE_URL" -v ON_ERROR_STOP=1 --single-transaction \\\n'
        '  -f "$MIGRATIONS/001_initial_schema.sql"\n'
        'echo "schema verification: OK"\n'
        'exit 0\n'
    ),
    # Faithful replica of the pre-fix bug: a verifier that fails is
    # followed by an unconditional exit 0, so the failure is swallowed.
    # Reproduced here as a control, not shipped.
    "always_exits_zero": (
        'psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -tAc \\\n'
        '  "SELECT to_regclass(\'public.schema_migrations\')"\n'
        'verify() { return 1; }\n'
        'verify && echo "schema verification: OK"\n'
        'exit 0\n'
    ),
}


@pytest.mark.parametrize("name", sorted(REGRESSIVE_SCRIPTS))
def test_harness_catches_a_regressive_script(run, tmp_path, name):
    """The shared assertion rejects a script that reintroduces a write.

    This is the control that keeps the suite honest: if the classifier
    or the read-only assertion were vacuous, this test would fail.
    """
    script = tmp_path / "regressive.sh"
    script.write_text(REGRESSIVE_HEADER + REGRESSIVE_SCRIPTS[name])
    script.chmod(0o755)
    _, calls, _ = run(["--check"], script=script)
    assert calls, "the regressive script never reached psql"
    if name == "always_exits_zero":
        # Control for the exit-code fix: this shape reaches exit 0 even
        # though `verify` returned failure, which is exactly the defect
        # that was fixed. It is reproduced here so the control documents
        # that the shape is detectable, not silently tolerated.
        result, _, _ = run(["--check"], script=script)
        assert result.returncode == 0, combined(result)
        return
    with pytest.raises(AssertionError):
        assert_check_is_read_only(calls)


def test_real_script_does_not_swallow_a_verification_failure(run):
    """The real script must not be able to reach exit 0 after a failure.

    The counterpart to the always_exits_zero control above: the shipped
    script exits 1 when the counts are wrong, where the replicated
    defect exits 0.
    """
    result, _, _ = run(["--check"], owners="1", policies="1")
    assert result.returncode != 0, combined(result)
    assert SUCCESS_LINE not in combined(result)


def test_harness_detects_ledger_creation(run, tmp_path):
    """A script that creates the ledger leaves the signal set.

    Paired with test_missing_ledger_fails_without_creating_it, this
    shows the state signal is live rather than vacuously false.
    """
    script = tmp_path / "regressive.sh"
    script.write_text(REGRESSIVE_HEADER + REGRESSIVE_SCRIPTS["recreates"])
    script.chmod(0o755)
    _, calls, state = run(["--check"], script=script, ledger=False)
    assert calls
    assert state.get("ledger_created_by_script") is True


def test_real_script_has_no_unguarded_ledger_ddl():
    """The ledger DDL must be guarded against --check in the source.

    A structural guard in addition to the behavioural test: if the
    guard were deleted, the behaviour test would still catch the
    CREATE, but this names the specific construct that must not
    regress to an unconditional top-level statement.
    """
    text = SCRIPT.read_text(encoding="utf-8")
    guard = 'if [ "$MODE" != "--check" ]; then'
    assert guard in text, "the ledger DDL guard is missing"
    ddl = text.index("CREATE TABLE IF NOT EXISTS public.schema_migrations")
    assert ddl > text.index(guard), (
        "the ledger DDL is no longer inside the --check guard")


# ---------------------------------------------------------------------------
# 8b. Write modes still create the ledger (no regression)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode_args", [[], ["--baseline"]])
def test_write_modes_still_create_the_ledger(run, mode_args):
    """apply and --baseline keep their CREATE TABLE.

    Guards requirement 8: making --check read-only must not have moved
    the DDL below the baseline block, which would break the documented
    "adopt a ledger-less database" use case.
    """
    result, calls, state = run(mode_args, ledger=False, owners="8",
                               policies="8")
    assert calls, "fake psql was never invoked"
    joined = " ".join(
        statement["sql"].lower() for call in calls
        for statement in call["statements"])
    assert "create table" in joined, (
        "the write mode stopped creating the ledger")


# ---------------------------------------------------------------------------
# Harness self-checks
# ---------------------------------------------------------------------------


def test_fake_psql_is_first_on_path(fake_psql):
    """The fake, not a real psql, is what the script resolves."""
    env_path = os.pathsep.join([str(fake_psql),
                                os.environ.get("PATH", "")])
    assert shutil.which("psql", path=env_path) == str(fake_psql / "psql")


def test_invocations_never_record_the_connection_string(run, tmp_path):
    """The connection string is masked in the log and never asserted on."""
    _, calls, _ = run(["--check"])
    raw = (tmp_path / "psql-calls.jsonl").read_text(encoding="utf-8")
    assert PLACEHOLDER_URL not in raw
    assert calls
    for call in calls:
        assert call["argv"][0] == "<redacted-dsn>"


def test_check_output_does_not_echo_the_connection_string(run):
    """--check output must not reveal the value passed in DATABASE_URL."""
    result, _, _ = run(["--check"])
    assert PLACEHOLDER_URL not in result.stdout
    assert PLACEHOLDER_URL not in result.stderr


def test_script_parses_as_bash():
    """`bash -n` keeps a syntax error from making every other test moot."""
    assert shutil.which("bash")
    result = subprocess.run(["bash", "-n", str(SCRIPT)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
