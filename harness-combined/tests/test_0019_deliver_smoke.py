"""
Content-verification tests for context/flows/deliver-ticket.md — spec 0019-post-merge-smoke-test.
Verifies the deliver flow documents the post-merge smoke-test phase (Step 4b), the config read in
Step 3, the SHA captures in Step 4, and the deferred publish/cleanup (Step 4c).
"""
from pathlib import Path

FLOW_FILE = Path(__file__).parent.parent / "context" / "flows" / "deliver-ticket.md"


def _content() -> str:
    return FLOW_FILE.read_text()


def _section(content: str, start: str, end: str | None = None) -> str:
    i = content.find(start)
    assert i >= 0, f"Section '{start}' not found"
    if end is None:
        return content[i:]
    j = content.find(end, i + len(start))
    return content[i:j] if j >= 0 else content[i:]


def test_flow_file_exists():
    assert FLOW_FILE.exists(), "context/flows/deliver-ticket.md must exist"


# --- Step 3: config read once + confirmation display (FR-1, FR-2, FR-4, FR-10) ---

def test_step3_reads_config_once():
    step3 = _section(_content(), "## Step 3 — Confirm", "## Step 4 —")
    assert "Read smoke-test config once here" in step3
    assert "do **not** re-read" in step3, "Step 3 must state config is not re-read in Step 4b"


def test_step3_documents_all_three_keys_and_defaults():
    step3 = _section(_content(), "## Step 3 — Confirm", "## Step 4 —")
    for key in ("smoke_test_command", "smoke_test_mode", "smoke_test_timeout"):
        assert key in step3, f"Step 3 must document {key}"
    assert "auto-revert" in step3 and "warn-only" in step3
    assert "default 60" in step3
    assert "cap at 300" in step3, "Step 3 must document the 300s cap-with-warning"
    assert "non-integer/zero/negative" in step3, "Step 3 must document the invalid-timeout skip"


def test_step3_confirmation_displays_smoke_details():
    step3 = _section(_content(), "## Step 3 — Confirm", "## Step 4 —")
    assert "[smoke test: <smoke_test_command>" in step3, \
        "confirmation block must surface the smoke command/mode/timeout when configured"


# --- Step 4: SHA capture (FR-7a, FR-11) ---

def test_step4_captures_both_shas():
    step4 = _section(_content(), "## Step 4 —", "## Step 4b —")
    assert "pre_merge_sha=$(git rev-parse HEAD)" in step4, "pre-merge SHA must be captured before merge"
    assert "merge_commit_sha=$(git rev-parse HEAD)" in step4, "merge-commit SHA must be captured after commit"


# --- Step 4b: the smoke-test phase ---

def _step4b() -> str:
    return _section(_content(), "## Step 4b — Post-merge smoke test", "## Step 4c —")


def test_step4b_positioned_after_step4_before_step5():
    c = _content()
    assert c.find("## Step 4 —") < c.find("## Step 4b —") < c.find("## Step 4c —") < c.find("## Step 5 —"), \
        "Step 4b/4c must sit between the merge (Step 4) and learnings (Step 5)"


def test_step4b_runs_before_cleanup():
    b = _step4b()
    assert "before Step 4c publish/cleanup" in b
    assert "survive a failure" in b, "Step 4b must state branch/worktree survive a failure"


def test_step4b_concurrency_guard_active_sentinel():
    b = _step4b()
    assert ".tickets/.active" in b
    assert "DELIVERY HALTED" in b
    assert "another delivery is in progress (<active-ticket>); resolve before retrying" in b
    assert "run no smoke test and no revert" in b


def test_step4b_subprocess_execution_safety():
    b = _step4b()
    assert "shlex.split(smoke_test_command)" in b
    assert "shell=False" in b
    assert "os.setsid()" in b, "smoke command must run in its own process group"
    assert "literal arguments" in b, "shell metacharacters must be documented as literal arguments"
    for meta in ("`|`", "`>`", "`<`", "`&&`", "`;`"):
        assert meta in b, f"metacharacter {meta} must be listed"


def test_step4b_env_allowlist():
    b = _step4b()
    assert "never `None`" in b, "env dict must be explicit, never None"
    for key in ("`PATH`", "`HOME`", "`SHELL`", "`TERM`", "`USER`", "`LANG`"):
        assert key in b, f"env allowlist must include {key}"
    assert 're.match(r"^LC_", k)' in b, "LC_* keys must be materialized via re.match"
    assert "AWS_SECRET_ACCESS_KEY" in b and "excluded" in b, "sensitive vars must be documented as excluded"


def test_step4b_timeout_killpg_escalation():
    b = _step4b()
    assert "os.killpg(os.getpgid(proc.pid), signal.SIGTERM)" in b
    assert "SIGKILL" in b
    assert "no `sleep`-polling" in b
    assert "timeout + 10" in b, "total kill window must be bounded to timeout + 10s"
    assert "Treat a timeout as a non-zero exit" in b


def test_step4b_exit_zero_continues():
    b = _step4b()
    assert "Exit 0" in b
    assert "Steps 5–10 proceed unchanged" in b


def test_step4b_auto_revert_path():
    b = _step4b()
    assert "git revert -m 1 --no-edit <merge_commit_sha>" in b
    assert "status: implementing" in b
    assert "leave the branch and worktree intact" in b
    assert "SMOKE TEST FAILED" in b
    assert "main reverted to <pre_merge_sha>" in b
    assert "truncated to 2000 chars" in b


def test_step4b_auto_revert_failure_halts():
    b = _step4b()
    assert "AUTO-REVERT FAILED" in b
    assert "manual intervention required: git revert -m 1 --no-edit <merge_commit_sha>" in b
    assert "halt without proceeding to Steps 5–10" in b


def test_step4b_warn_only_path():
    b = _step4b()
    assert "warn-only" in b
    assert "before** cleanup" in b, "warn-only must store the failure signal before cleanup"
    assert "survives the branch and worktree deletion" in b


# --- Step 4c: deferred publish/cleanup ---

def test_step4c_deferred_publish_cleanup():
    c = _section(_content(), "## Step 4c — Publish and clean up", "## Step 5 —")
    assert "not** run on an `auto-revert` failure" in c, \
        "Step 4c must be skipped on auto-revert failure"
    assert "git push" in c
    assert "git worktree remove" in c
    assert "git branch -D" in c
