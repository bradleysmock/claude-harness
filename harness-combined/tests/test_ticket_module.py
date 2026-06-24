# harness-combined/tests/test_ticket_module.py
from pathlib import Path
import ticket


def _mk(root: Path, name: str) -> None:
    (root / name).mkdir(parents=True)
    (root / name / "status.md").write_text("status: solution\n", encoding="utf-8")


def test_next_number_empty(tmp_path: Path) -> None:
    (tmp_path / ".tickets").mkdir()
    assert ticket.next_number(tmp_path / ".tickets") == 1


def test_next_number_scans_active_and_completed(tmp_path: Path) -> None:
    tickets = tmp_path / ".tickets"
    _mk(tickets, "0001-alpha")
    _mk(tickets, "completed/0007-archived")
    _mk(tickets, "0003-beta")
    assert ticket.next_number(tickets) == 8  # max(1,3,7)+1, completed counts


def test_format_number_zero_pads() -> None:
    assert ticket.format_number(8) == "0008"


def test_parse_status_reads_fields(tmp_path: Path) -> None:
    f = tmp_path / "status.md"
    f.write_text("status: implementing\nticket: 0008\nowner: a@b.c\n", encoding="utf-8")
    parsed = ticket.parse_status(f)
    assert parsed["status"] == "implementing"
    assert parsed["owner"] == "a@b.c"
