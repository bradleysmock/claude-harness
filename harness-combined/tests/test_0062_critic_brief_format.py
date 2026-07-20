"""Content-verification test for ticket 0062's critic-brief.md header-format mandate.

Real critic output previously varied in structure (e.g. a `### SEVERITY-N — title`
heading with separate labeled Panel/Files lines), which
`gates/critic_finding_parser.py`'s `parse_critic_findings` cannot parse — silently
producing zero findings and, downstream, an always-empty reconciliation summary.
This asserts critic-brief.md now mandates the exact single-line header grammar the
parser expects.
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent
CRITIC_BRIEF = ROOT / "context" / "critic-brief.md"


def _step4_text() -> str:
    text = CRITIC_BRIEF.read_text()
    start = text.index("## Step 4 —")
    end = text.index("\n---\n", start)
    return text[start:end]


def test_exact_header_template_present():
    section = _step4_text()
    assert "**SEVERITY** · <Panel> / <Dimension> · `<file>:<line>`" in section


def test_bold_close_immediately_after_severity_mandated():
    section = _step4_text()
    assert "bold-closed immediately after the word" in section
    assert "never `**BLOCKER-1" in section
