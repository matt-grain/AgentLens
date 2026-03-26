"""HTML report generator for evaluation results."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from agentlens.models.evaluation import EvalLevel, EvalSummary
from agentlens.models.trace import Trace

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_LEVEL_ORDER: list[EvalLevel] = [
    EvalLevel.BUSINESS,
    EvalLevel.BEHAVIOR,
    EvalLevel.RISK,
    EvalLevel.OPERATIONAL,
]


def generate_html_report(summary: EvalSummary, trace: Trace, output_path: Path) -> None:
    """Render the HTML report and write it to output_path."""
    html = render_html_report(summary, trace)
    output_path.write_text(html, encoding="utf-8")


def render_html_report(summary: EvalSummary, trace: Trace) -> str:
    """Return rendered HTML as a string."""
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("report.html.j2")
    return template.render(
        summary=summary,
        trace=trace,
        level_order=_LEVEL_ORDER,
        score_class=_score_class,
        score_pct=_score_pct,
    )


def _score_class(score: float) -> str:
    """Return a CSS class name based on the score."""
    if score >= 0.8:
        return "pass"
    if score >= 0.5:
        return "warn"
    return "fail"


def _score_pct(score: float) -> str:
    """Format score as a percentage string."""
    return f"{score:.0%}"
