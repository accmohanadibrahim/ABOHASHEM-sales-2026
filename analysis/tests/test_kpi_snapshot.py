"""The rebuild PR's before/after table has to cover what the app shows.

kpi_snapshot.py is what turns a wall of regenerated CSV into a reviewable
change. Its failure mode is silent and specific: a section ships, nobody adds
its headline figure here, and from then on every rebuild PR reports "nothing
changed" for that section however far the numbers move. These tests fix the
coverage in place so that stops being possible by accident.

Standard library only, like the tool itself — it runs in CI before the pipeline
dependencies are installed.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "analysis" / "tools" / "kpi_snapshot.py"
DASH = ROOT / "data" / "processed" / "margin_dashboard.json"
TOL = 0.01


def _tool():
    spec = importlib.util.spec_from_file_location("kpi_snapshot", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


K = _tool()


def test_the_tool_imports_without_the_pipeline_dependencies():
    """It runs before `pip install`, so a heavy import here breaks the workflow.

    rebuild-on-data.yml captures the BEFORE snapshot as its first step,
    deliberately ahead of installing anything — otherwise a failed install would
    also cost the comparison.
    """
    import sys
    saved = {name: sys.modules.get(name) for name in
             ("polars", "openpyxl", "pandas", "numpy", "fitz", "pymupdf")}
    try:
        for name in saved:
            sys.modules[name] = None
        assert _tool().capture(), "capture() must work with no third-party module"
    finally:
        for name, was in saved.items():
            if was is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = was


def test_every_shipped_section_has_a_headline_figure():
    """One metric per area the app actually reports.

    Spelled out rather than counted, so adding a section without a metric fails
    with the name of what is missing instead of an off-by-one.
    """
    captured = K.capture()
    for label in ("الإيراد الإجمالي",            # sales
                  "المديونية القائمة",           # receivables
                  "المتأخرات",                   # overdue
                  "متأخر 31–60 يومًا",           # aging bands
                  "حدّ التأخّر المشتقّ",          # the derived cutoff
                  "هامش مجمل — مقيس %",          # profitability
                  "إجمالي المصروفات",            # expenses
                  "مصروفات تشغيلية",             # …and each category
                  "مصروفات إدارية وعمومية",
                  "مصروفات بيعية وتسويقية",
                  "مصروفات بنكية وتمويلية"):
        assert label in captured, f"no headline figure captured for «{label}»"


def test_the_expense_total_is_the_statements_own_total():
    """Summed here the way the app sums it — and it must agree with the source."""
    if not DASH.exists():
        pytest.skip("margin_dashboard.json is not in this checkout")
    doc = json.loads(DASH.read_text(encoding="utf-8"))
    rows = doc["statements"]["expenses"]["by_statement"]
    got = K.expense_metrics(doc)["إجمالي المصروفات"]["value"]
    assert abs(got - sum(r["total_expenses"] for r in rows)) <= TOL


def test_each_category_matches_the_payload():
    if not DASH.exists():
        pytest.skip("margin_dashboard.json is not in this checkout")
    doc = json.loads(DASH.read_text(encoding="utf-8"))
    want: dict = {}
    for row in doc["statements"]["expenses"]["by_statement"]:
        for key, value in (row.get("categories") or {}).items():
            want[key] = want.get(key, 0.0) + value
    got = K.expense_metrics(doc)
    for key, label in K.EXPENSE_CATEGORIES.items():
        assert abs(got[label]["value"] - want[key]) <= TOL, label


def test_a_missing_input_is_recorded_as_missing_and_never_raises():
    """This tool must never be the reason a rebuild fails.

    A capture taken before the pipeline has ever run, or against a checkout
    missing an output, reports «—» for that row. Raising instead would lose the
    comparison for every OTHER metric too.
    """
    for empty in (None, {}, {"statements": {}}, {"statements": {"expenses": {}}}):
        out = K.expense_metrics(empty)
        assert all(m["value"] is None for m in out.values())


def test_a_text_metric_diffs_without_pretending_to_be_a_number():
    """The two dates are text on purpose; a percentage change of a date is noise."""
    label = "تاريخ اللقطة (as-of)"
    before = {label: {"value": "2026-09-03", "kind": "text"}}
    after = {label: {"value": "2026-10-01", "kind": "text"}}

    row = next(ln for ln in K.diff(before, after).splitlines() if label in ln)
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells[1:3] == ["2026-09-03", "2026-10-01"], row
    assert cells[3] == "تغيّر", f"a date delta must not be arithmetic: {row}"

    # …and an unchanged date must read as unchanged, not as a change to itself.
    same = next(ln for ln in K.diff(before, before).splitlines() if label in ln)
    assert [c.strip() for c in same.strip("|").split("|")][3] == "بلا تغيير"
