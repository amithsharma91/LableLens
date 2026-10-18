"""Regression guard: local credential helpers stay out of Git and Docker.

Task 0.1. Fully offline: no network, no Docker daemon, no database, and
no credential value is ever read. On a developer machine
``backend/get_supabase_token.sh`` and ``backend/.supabase-auth.env``
carry live Supabase authentication material, so they must never be
staged for commit and must never enter a Docker build context.

Every positive assertion is paired with a control that must behave the
opposite way, so deleting an exclusion rule fails this module instead of
silently passing.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

# backend/app/tests/unit/test_secret_paths_are_ignored.py
#   parents[0] backend/app/tests/unit
#   parents[1] backend/app/tests
#   parents[2] backend/app
#   parents[3] backend
#   parents[4] repository root
REPO_ROOT = Path(__file__).resolve().parents[4]

SECRET_RELPATHS = (
    "backend/get_supabase_token.sh",
    "backend/.supabase-auth.env",
)

# Tracked, non-secret source file. Every "must be excluded" assertion is
# paired with this path, which must stay visible to both Git and Docker.
CONTROL_RELPATH = "backend/app/serve.py"

DOCKERIGNORE = REPO_ROOT / ".dockerignore"


# ---------------------------------------------------------------------------
# git plumbing (read-only helpers)
# ---------------------------------------------------------------------------


def _require_repo():
    """Fail loudly when the git premises of this module do not hold.

    These assertions guard a security control. If git is unavailable or
    the tree is not a repository they cannot be evaluated, and skipping
    would silently turn the control into a no-op.
    """
    if shutil.which("git") is None:
        pytest.fail("git is not on PATH; ignore rules cannot be verified")
    if not (REPO_ROOT / ".git").exists():
        pytest.fail("no .git marker at %s; not a work tree" % REPO_ROOT)
    probe = _run("rev-parse", "--show-toplevel")
    if probe.returncode != 0:
        pytest.fail("git rev-parse failed: %s" % probe.stderr.strip())
    if Path(probe.stdout.strip()).resolve() != REPO_ROOT:
        pytest.fail("git top level is not %s" % REPO_ROOT)


def _run(*args):
    """Run a read-only git command against the repository root.

    ``-C REPO_ROOT`` is used rather than ``cwd=`` so the result never
    depends on the directory pytest was invoked from. Only flags that
    cannot write the index or the working tree are ever passed here.
    """
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT)] + list(args),
        capture_output=True,
        text=True,
        timeout=120,
    )


def _check_ignore_quiet(relpath):
    """True when git ignores ``relpath``.

    ``--quiet`` is used deliberately: ``-v`` exits 0 whenever *any*
    pattern matches, including a ``!`` negation, so an exit-code-only
    assertion on ``-v`` would accept a negated match as "ignored".
    """
    proc = _run("check-ignore", "--quiet", "--no-index", "--", relpath)
    if proc.returncode not in (0, 1):
        pytest.fail("git check-ignore failed: %s" % proc.stderr.strip())
    return proc.returncode == 0


def _ignore_rule(relpath):
    """Return ``(source, pattern)`` of the rule matching ``relpath``."""
    proc = _run("check-ignore", "-v", "--no-index", "--", relpath)
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    head = proc.stdout.split("\t", 1)[0]
    source, _, pattern = head.partition(":")
    line_no, _, pattern = pattern.partition(":")
    return source, pattern


# ---------------------------------------------------------------------------
# 1 + 2: the secret paths are matched by a committed Git ignore rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relpath", SECRET_RELPATHS)
def test_secret_path_is_git_ignored(relpath):
    """Positive: the rule exists. Delete it and this fails."""
    assert _check_ignore_quiet(relpath), (
        "%s is not ignored by any git rule" % relpath
    )


@pytest.mark.parametrize("relpath", SECRET_RELPATHS)
def test_ignore_rule_is_not_a_negation(relpath):
    """A ``!`` pattern reports rc 0 under ``-v`` but ignores nothing."""
    rule = _ignore_rule(relpath)
    assert rule is not None, "no rule matched %s" % relpath
    _source, pattern = rule
    assert not pattern.startswith("!"), (
        "%s matched negation %r, so it is NOT ignored" % (relpath, pattern)
    )


@pytest.mark.parametrize("relpath", SECRET_RELPATHS)
def test_ignore_rule_comes_from_a_committed_file(relpath):
    """The rule must live in a tracked file, not a global excludes file.

    Without this, a developer whose global gitignore carried the entry
    would pass locally while a fresh clone stayed unprotected.
    """
    rule = _ignore_rule(relpath)
    assert rule is not None, relpath
    source, _pattern = rule
    resolved = (REPO_ROOT / source).resolve()
    assert resolved.is_file(), "ignore source %r is not a file" % source
    inside = resolved.relative_to(REPO_ROOT)
    assert ".git" not in inside.parts, (
        "rule came from uncommitted %s" % inside
    )


def test_control_path_is_not_git_ignored():
    """Negative control: tracked source code must stay visible to git."""
    assert not _check_ignore_quiet(CONTROL_RELPATH), (
        "%s is ignored; the ignore rules are over-broad"
        % CONTROL_RELPATH
    )


def test_tracked_ops_scripts_are_not_git_ignored():
    """Second control: containment must not hide deploy/migrate tooling.

    Both files are tracked, and a broad ``*.sh`` rule would make any new
    script silently invisible to ``git add``.
    """
    for relpath in ("scripts/deploy_staging.sh",
                    "scripts/migrate_staging.sh"):
        assert not _check_ignore_quiet(relpath), (
            "%s is ignored; containment must not hide ops tooling"
            % relpath
        )


# ---------------------------------------------------------------------------
# 3: `git add` never proposes the secret paths
# ---------------------------------------------------------------------------

_ADD_LINE = re.compile(r"^add '(?P<path>.*)'$")


def _proposed_paths(stdout):
    """Repo-relative paths that ``git add --dry-run`` would stage.

    The return code is deliberately ignored: git exits 1 when a pathspec
    names an ignored file, which is exactly the desired state here.
    """
    found = set()
    for line in stdout.splitlines():
        match = _ADD_LINE.match(line.strip())
        if match is not None:
            found.add(match.group("path"))
    return found


def test_proposed_paths_parser_reads_real_git_output():
    """Unit control: prove the parser extracts paths on a literal sample."""
    sample = "\n".join((
        "add 'backend/get_supabase_token.sh'",
        "add 'backend/.supabase-auth.env'",
        "remove 'docs/retired.md'",
        "add 'backend/app/serve.py'",
    ))
    assert _proposed_paths(sample) == {
        "backend/get_supabase_token.sh",
        "backend/.supabase-auth.env",
        "backend/app/serve.py",
    }


def test_git_add_dry_run_does_not_propose_secret_paths():
    """Positive: a routine ``git add -A`` skips both secret paths.

    Scoped with ``--`` to the two pathspecs so unrelated dirty files in
    the tree cannot make this flaky, and asserted per-path rather than
    on emptiness so a dirty tree stays green.
    """
    proc = _run("add", "-A", "--dry-run", "--", *SECRET_RELPATHS)
    if proc.returncode == 128 and "index.lock" in proc.stderr:
        pytest.skip("another git process holds the index lock")
    proposed = _proposed_paths(proc.stdout)
    for relpath in SECRET_RELPATHS:
        assert relpath not in proposed, (
            "git add -A would stage %s (proposed: %s)"
            % (relpath, sorted(proposed))
        )


def test_forced_dry_run_control_proves_the_add_harness_is_live():
    """Negative control: ``-f`` proves git really reports these paths.

    ``--dry-run`` still writes nothing, so forcing the ignore rule aside
    is safe. This is the deterministic proof that the invocation above
    would surface a staged secret if one existed.
    """
    present = [
        relpath for relpath in SECRET_RELPATHS
        if (REPO_ROOT / relpath).exists()
    ]
    if not present:
        pytest.skip("no local secret file present to force-add")
    proc = _run("add", "-A", "--dry-run", "-f", "--", *present)
    if proc.returncode == 128 and "index.lock" in proc.stderr:
        pytest.skip("another git process holds the index lock")
    assert proc.returncode == 0, proc.stderr.strip()
    assert _proposed_paths(proc.stdout) == set(present), proc.stdout


# ---------------------------------------------------------------------------
# 4: the secret paths are excluded from the Docker build context
# ---------------------------------------------------------------------------


def _docker_regex(pattern):
    """Translate one .dockerignore pattern into an anchored regex.

    Mirrors moby/patternmatcher: Go ``filepath.Match`` semantics where
    ``*`` and ``?`` do not cross ``/`` and ``[...]`` is a character
    class, plus ``**`` spanning any number of directories. The trailing
    group makes a pattern also exclude everything beneath a matching
    directory, which is why ``backend/app/tests/`` drops a whole tree.
    """
    out = ["^"]
    index = 0
    size = len(pattern)
    while index < size:
        char = pattern[index]
        if char == "*":
            end = index
            while end < size and pattern[end] == "*":
                end += 1
            before = pattern[index - 1] if index else ""
            after = pattern[end] if end < size else ""
            if end - index >= 2 and before in ("", "/") and after in ("", "/"):
                if after == "/":
                    out.append("(?:.*/)?")
                    end += 1
                else:
                    out.append(".*")
                index = end
                continue
            out.append("[^/]*")
            index = end
            continue
        if char == "?":
            out.append("[^/]")
        elif char == "[":
            end = index + 1
            if end < size and pattern[end] in ("!", "^"):
                end += 1
            if end < size and pattern[end] == "]":
                end += 1
            while end < size and pattern[end] != "]":
                end += 1
            if end >= size:
                out.append(re.escape("["))
            else:
                body = pattern[index + 1:end]
                if body[:1] in ("!", "^"):
                    body = "^" + body[1:]
                out.append("[" + body.replace("\\", "\\\\") + "]")
                end += 1
            index = end
            continue
        else:
            out.append(re.escape(char))
        index += 1
    out.append("(?:/.*)?$")
    return re.compile("".join(out))


def _docker_patterns(text):
    """Compile a .dockerignore file into ordered (negated, regex) rules."""
    rules = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        if negated:
            line = line[1:].strip()
        line = line.strip("/")
        while line.startswith("./"):
            line = line[2:]
        line = line.rstrip("/")
        if not line:
            continue
        rules.append((negated, _docker_regex(line)))
    return rules


def _docker_ignores(rules, relpath):
    """Last matching rule wins, exactly like Docker's matcher."""
    ignored = False
    for negated, regex in rules:
        if regex.match(relpath.strip("/")):
            ignored = not negated
    return ignored


def _compiled_dockerignore():
    assert DOCKERIGNORE.is_file(), "missing %s" % DOCKERIGNORE
    return _docker_patterns(DOCKERIGNORE.read_text())


def test_dockerignore_excludes_secret_paths():
    """Positive: neither credential file reaches the build context.

    The build context is the repository root
    (``docker build -f backend/Dockerfile .``), so patterns are matched
    against these repo-relative paths.
    """
    rules = _compiled_dockerignore()
    for relpath in SECRET_RELPATHS:
        assert _docker_ignores(rules, relpath), (
            "%s is inside the Docker build context" % relpath
        )


def test_dockerignore_excludes_local_env_file():
    """The pre-existing bare ``.env`` rule never matched ``backend/.env``.

    Docker patterns are context-root relative, so ``.env`` only ever
    matched a repository-root file. This pins the corrected behaviour.
    """
    rules = _compiled_dockerignore()
    assert _docker_ignores(rules, "backend/.env"), (
        "backend/.env is inside the Docker build context"
    )


def test_dockerignore_keeps_the_control_path_in_the_context():
    """Negative control: runtime code must still ship in the image."""
    rules = _compiled_dockerignore()
    assert not _docker_ignores(rules, CONTROL_RELPATH), (
        "%s is wrongly excluded from the image" % CONTROL_RELPATH
    )


def test_dockerignore_keeps_ops_scripts_out_of_the_context():
    """The Dockerfile never copies scripts/, so excluding them is safe."""
    rules = _compiled_dockerignore()
    for relpath in ("scripts/deploy_staging.sh",
                    "scripts/migrate_staging.sh"):
        assert not _docker_ignores(rules, relpath), (
            "%s is wrongly excluded" % relpath
        )


# Docker ignore semantics: literal expectations, so the file-level
# exclusions above cannot pass because the matcher is a no-op.
DOCKER_PATTERN_SEMANTICS = (
    # Patterns are context-root relative, not basename relative. These
    # two rows are the trap that makes gitignore-style rules fail here.
    (("*.env",), ".env", True),
    (("*.env",), "backend/.env", False),
    ((".env",), ".env", True),
    ((".env",), "backend/.env", False),
    # ** is the only recursive operator.
    (("**/*.env",), "backend/.env", True),
    (("**/*.env",), ".env", True),
    # A matching directory also excludes everything below it.
    (("backend/app/tests",), "backend/app/tests/unit/test_x.py", True),
    (("backend/app/tests",), "backend/app/serve.py", False),
    # A leading slash is stripped: it means context-root relative.
    (("/backend/.env",), "backend/.env", True),
    # Both credential spellings must work against the real targets.
    (("*.sh",), "backend/get_supabase_token.sh", False),
    (("**/*.sh",), "backend/get_supabase_token.sh", True),
    (("/backend/get_supabase_token.sh",), "backend/get_supabase_token.sh",
     True),
    (("/backend/.supabase-auth.env",), "backend/.supabase-auth.env", True),
    # filepath.Match semantics: ? and [...] do not cross a separator.
    (("a?c",), "abc", True),
    (("a?c",), "a/c", False),
    (("[ab]c",), "ac", True),
    (("[ab]c",), "cc", False),
    # ** spans zero or more directories.
    (("a/**/c",), "a/c", True),
    (("a/**/c",), "a/b/c", True),
    (("a/**/c",), "a/b/x/d", False),
)


@pytest.mark.parametrize(
    "patterns,relpath,want",
    DOCKER_PATTERN_SEMANTICS,
)
def test_docker_pattern_matcher_follows_docker_semantics(
    patterns, relpath, want
):
    """Unit control: prove the matcher on literal, file-free cases."""
    rules = _docker_patterns("\n".join(patterns))
    assert _docker_ignores(rules, relpath) is want, (
        "%r should %s %s" % (patterns, "match" if want else "skip", relpath)
    )


def test_dockerignore_names_the_secret_paths_literally():
    """Docker needs the full repo-relative path, so require it literally.

    Git and Docker disagree here. Git matches a slash-less pattern
    against the basename at any depth, so ``.supabase-auth.env`` alone
    is sufficient there. Docker matches against the path relative to
    the build context root, where a bare ``.supabase-auth.env`` would
    never match ``backend/.supabase-auth.env``. The behavioural tests
    above carry the weight; this one fails with a clear message.
    """
    docker_lines = DOCKERIGNORE.read_text().splitlines()
    for relpath in SECRET_RELPATHS:
        assert any(relpath in line for line in docker_lines), (
            ".dockerignore must name the repo-relative path %s" % relpath
        )


@pytest.mark.parametrize("relpath", SECRET_RELPATHS)
def test_secret_rule_resolves_to_a_path_covering_the_target(relpath):
    """The rule that actually fires must really cover this target.

    Checks the responsible pattern rather than raw file text, because
    the legitimate Git form is a slash-less basename that matches at any
    depth. Guards against a rule that matches for an unrelated reason.
    """
    rule = _ignore_rule(relpath)
    assert rule is not None, "no rule matched %s" % relpath
    _source, pattern = rule
    if pattern.startswith("/"):
        candidate = pattern.lstrip("/")
    elif "/" not in pattern:
        candidate = relpath.rsplit("/", 1)[-1]
    else:
        candidate = pattern
    assert candidate in relpath or candidate == relpath.rsplit("/", 1)[-1], (
        "rule %r does not cover %s" % (pattern, relpath)
    )
