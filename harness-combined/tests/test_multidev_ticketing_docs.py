from pathlib import Path

ROOT = Path(__file__).parent.parent


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ── Task 5: problem.md claim phase ──────────────────────────────
def test_problem_claim_uses_helper() -> None:
    c = read("commands/problem.md")
    assert "ticket claim" in c or "ticket.py claim" in c


def test_problem_claim_sets_claimed_status() -> None:
    assert "status: claimed" in read("commands/problem.md")


def test_problem_records_owner() -> None:
    assert "owner:" in read("commands/problem.md")


def test_problem_no_longer_references_next_ticket() -> None:
    assert "NEXT_TICKET" not in read("commands/problem.md")


def test_problem_claim_pushes() -> None:
    c = read("commands/problem.md")
    assert "git push" in c or "--push" in c
