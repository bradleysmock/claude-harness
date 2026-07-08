"""Content-verification tests for the progress-checklist feature (ticket 0002).

This ticket modifies markdown instruction files, not Python code. These tests
verify that the shared "Progress checklist" convention, the per-flow checklist
blocks (each opening with the unique sentinel), the byte-identical shared
labels, and the sub-flow notes are present — and that the sentinel appears in
*exactly* the eight flow files and nowhere else under commands/, context/flows/,
or skills/.

Limitation: these tests verify the instructions exist, not that the model calls
TodoWrite at runtime. The reliability criterion is discharged manually.
"""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent

SENTINEL = "<!-- progress-checklist -->"

# The eight flow files that must carry the sentinel (FR-2 / FR-5).
SENTINEL_FILES = [
    "context/flows/autopilot-ticket.md",
    "context/flows/autopilot-batch.md",
    "context/flows/build-ticket.md",
    "context/flows/build-spec.md",
    "commands/problem.md",
    "context/flows/write-spec-ticket.md",
    "context/flows/write-spec-spec.md",
    "context/flows/deliver-ticket.md",
]

# Expected stage labels per flow (FR-2). Shared labels are byte-identical (FR-3).
EXPECTED_LABELS = {
    "context/flows/autopilot-ticket.md": [
        "Generate specs (if needed)",
        "Build XXXX in worktree",
        "Critic + auto-repair",
        "Merge worktree",
        "Status → done + archive",
        "Cleanup",
    ],
    "context/flows/autopilot-batch.md": [
        "Create integration worktree",
        "Build members in order",
        "Combined critic + auto-repair",
        "Batch deliver (1 push)",
        "Cleanup",
    ],
    "context/flows/build-ticket.md": [
        "Generate specs (if needed)",
        "Build XXXX in worktree",
        "Critic + auto-repair",
        "Present diff (Checkpoint 2)",
    ],
    "context/flows/deliver-ticket.md": [
        "Merge worktree",
        "Status → done + archive",
        "Cleanup",
    ],
    "context/flows/build-spec.md": [
        "Generate spec (if needed)",
        "Run gate engine",
        "Produce artifact",
    ],
    "commands/problem.md": [
        "Clarity check",
        "Claim ticket",
        "Problem",
        "Requirements",
        "Tech-stack advisor (if new app)",
        "Solution",
        "Critic loop",
        "Checkpoint 1",
    ],
    "context/flows/write-spec-ticket.md": [
        "Analyze (spec vs task DAG)",
        "Write spec(s)",
    ],
    "context/flows/write-spec-spec.md": [
        "Analyze (spec vs task DAG)",
        "Write spec(s)",
    ],
}


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def convention_section() -> str:
    """Return just the '## Progress checklist' section of harness-reference.md,
    from its heading to the next top-level heading (or EOF). Scopes content
    assertions so they pin the convention's own text, not stray mentions
    elsewhere in the document."""
    content = read("context/harness-reference.md")
    start = content.index("## Progress checklist")
    nxt = content.find("\n## ", start + 1)
    return content[start:] if nxt == -1 else content[start:nxt]


def block_after_sentinel(rel: str) -> str:
    """Return a flow file's checklist block: from the sentinel to the next
    '## ' heading (or EOF). Bounds the window structurally instead of by a
    fixed byte count."""
    content = read(rel)
    idx = content.index(SENTINEL)
    nxt = content.find("\n## ", idx)
    return content[idx:] if nxt == -1 else content[idx:nxt]


def labels(rel: str) -> list[str]:
    """Extract a flow's declared stage labels.

    The label line is the first backtick-wrapped line after the sentinel that
    contains the ' · ' separator. Split it on ' · ' (FR-3's comparison rule).
    """
    content = read(rel)
    idx = content.index(SENTINEL)
    after = content[idx + len(SENTINEL):]
    for line in after.splitlines():
        m = re.match(r"^\s*`(.+)`\s*$", line)
        if m and " · " in m.group(1):
            return m.group(1).split(" · ")
    raise AssertionError(f"no backticked label line found after sentinel in {rel}")


# ── FR-1: shared convention subsection exists ─────────────────────────────

def test_convention_subsection_exists() -> None:
    content = read("context/harness-reference.md")
    assert "## Progress checklist" in content


def test_convention_covers_mechanism() -> None:
    content = read("context/harness-reference.md")
    # TodoWrite as first action; one in_progress; completed on finish; short labels.
    assert "TodoWrite" in content
    assert "in_progress" in content
    assert "completed" in content


def test_convention_has_one_list_per_run_rule() -> None:
    # Scope to the convention section so the assertions actually pin the rule's
    # text — both filenames also appear elsewhere in harness-reference.md.
    section = convention_section()
    assert "One list per run" in section
    assert "sub-flow" in section
    # Names the two sub-flows the rule guards.
    assert "build-ticket.md" in section
    assert "deliver-ticket.md" in section


def test_convention_has_true_state_on_early_exit() -> None:
    content = read("context/harness-reference.md")
    assert "early exit" in content


# ── FR-2: sentinel + labels present in the eight flow files ───────────────

def test_sentinel_present_in_each_flow_file() -> None:
    for rel in SENTINEL_FILES:
        assert SENTINEL in read(rel), f"sentinel missing in {rel}"


def test_each_block_references_the_convention() -> None:
    for rel in SENTINEL_FILES:
        block = block_after_sentinel(rel)
        assert "Progress checklist" in block, f"convention reference missing in {rel}"
        assert "harness-reference.md" in block, f"convention pointer missing in {rel}"


def test_expected_labels_present_in_each_flow_file() -> None:
    for rel, expected in EXPECTED_LABELS.items():
        assert labels(rel) == expected, f"label mismatch in {rel}"


# ── FR-3: shared labels are byte-identical ────────────────────────────────

def test_build_and_autopilot_share_first_three_labels() -> None:
    build = labels("context/flows/build-ticket.md")
    autopilot = labels("context/flows/autopilot-ticket.md")
    assert build[:3] == autopilot[:3]
    assert build[:3] == [
        "Generate specs (if needed)",
        "Build XXXX in worktree",
        "Critic + auto-repair",
    ]


def test_deliver_and_autopilot_share_delivery_tail_labels() -> None:
    deliver = labels("context/flows/deliver-ticket.md")
    autopilot = labels("context/flows/autopilot-ticket.md")
    assert deliver == autopilot[-3:]
    assert deliver == ["Merge worktree", "Status → done + archive", "Cleanup"]


def test_write_spec_ticket_and_spec_share_labels() -> None:
    assert labels("context/flows/write-spec-ticket.md") == labels(
        "context/flows/write-spec-spec.md"
    )


# ── FR-4: sub-flow note in build-ticket and deliver-ticket ────────────────

def test_build_ticket_has_subflow_note() -> None:
    content = read("context/flows/build-ticket.md")
    assert "Sub-flow note" in content
    assert "/autopilot" in content
    assert "one-list-per-run" in content


def test_deliver_ticket_has_subflow_note() -> None:
    content = read("context/flows/deliver-ticket.md")
    assert "Sub-flow note" in content
    assert "/autopilot" in content
    assert "one-list-per-run" in content


# ── FR-5: exhaustive sentinel scan ────────────────────────────────────────

def _scan_dirs_for_sentinel() -> set[str]:
    found: set[str] = set()
    for root in ("commands", "context/flows", "skills"):
        base = ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if SENTINEL in text:
                found.add(path.relative_to(ROOT).as_posix())
    return found


def test_sentinel_appears_in_exactly_the_eight_files() -> None:
    assert _scan_dirs_for_sentinel() == set(SENTINEL_FILES)


def test_subflow_only_files_lack_sentinel() -> None:
    # stack-advisor.md and repair-escalation.md are sub-flow-only — no sentinel.
    for rel in ("context/flows/stack-advisor.md", "context/flows/repair-escalation.md"):
        assert SENTINEL not in read(rel), f"sentinel unexpectedly present in {rel}"
