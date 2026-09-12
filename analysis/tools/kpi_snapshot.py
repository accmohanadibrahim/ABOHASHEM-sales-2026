#!/usr/bin/env python3
"""Capture the headline numbers, and diff two captures into Markdown.

Used by the rebuild workflow so a pull request opened after new source files
land says what those files did to the figures, instead of showing a wall of
regenerated CSV and a 11 MB HTML blob and leaving the reviewer to guess.

    python3 analysis/tools/kpi_snapshot.py capture before.json
    ... regenerate ...
    python3 analysis/tools/kpi_snapshot.py capture after.json
    python3 analysis/tools/kpi_snapshot.py diff before.json after.json > body.md

Standard library only: it has to run before the pipeline's dependencies are
necessarily installed, and it must never be the reason a rebuild fails. Missing
inputs are recorded as missing rather than raised.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "data" / "processed"
MARGIN = P / "margin_dashboard.json"

# label -> (file, dotted path). A path segment that is an integer indexes a list.
METRICS = {
    "الإيراد الإجمالي": (P / "eda_summary.json", "total_revenue", "egp"),
    "عدد العملاء": (P / "eda_summary.json", "n_customers", "int"),
    "عدد الأصناف": (P / "eda_summary.json", "n_items", "int"),
    "عدد الشهور": (P / "eda_summary.json", "n_months", "int"),
    "عدد البنود": (P / "data_quality_metrics.json", "n_rows", "int"),
    "عدد الفواتير": (P / "data_quality_metrics.json", "n_invoices", "int"),
    "تغطية التكلفة %": (P / "margin_summary.json", "coverage.coverage_pct", "pct"),
    "إيراد غير مُسعَّر": (P / "margin_summary.json", "coverage.revenue_uncosted", "egp"),
    "هامش مجمل — مقيس %": (P / "margin_summary.json", "measured.gross_margin_pct", "pct"),
    "هامش تشغيلي — مقيس %": (P / "margin_summary.json", "measured.op_margin_pct", "pct"),
    "هامش مجمل — تقديري %": (P / "margin_summary.json", "indicative.gross_margin_pct", "pct"),
    "هامش تشغيلي — تقديري %": (P / "margin_summary.json", "indicative.op_margin_pct", "pct"),
    "شهور ضمن النافذة": (P / "margin_summary.json", "price_drift.reliable_months", "count"),
    # The statements/expenses block. Added after the section shipped: until it
    # was here, a round could re-read every income statement and the before/after
    # table would show nothing, because none of the metrics above touch them.
    "قوائم الدخل": (MARGIN, "statements.meta.n_observations", "int"),
    "قوائم بتفصيل بالبند": (MARGIN,
                            "statements.expenses.coverage.statements_with_item_detail", "int"),
    "أشهر بتفصيل بالبند": (MARGIN,
                           "statements.expenses.coverage.months_with_item_detail", "int"),
    "بنود مصروفات مميَّزة": (MARGIN, "statements.expenses.coverage.n_items", "int"),
    # Printed in the statements, summed by no group total, added to nothing.
    # A change in the count means a statement was re-read.
    "سطور خارج المجاميع": (MARGIN, "statements.expenses.rows_outside_totals", "count"),
    "مرادفات أسماء البنود": (MARGIN, "statements.expenses.aliases", "count"),
    "نافذة القوائم": (MARGIN, "statements.meta.statement_window", "text"),
}

DASH_JS = ROOT / "executive_dashboard" / "data.js"
DASH_METRICS = {
    "المديونية القائمة": ("receivables.total_outstanding", "egp"),
    "المتأخرات": ("receivables.total_overdue", "egp"),
    "إجمالي التحصيل": ("collections.grand_total_collected", "egp"),
    "إجمالي المرتجعات": ("collections.grand_total_returns", "egp"),
    # The aging block. The two dates are carried as text on purpose: re-dating a
    # snapshot moves every band at once, and seeing the dates move in the same
    # table says the bands moved for that reason rather than for a data reason.
    "تاريخ اللقطة (as-of)": ("receivables.as_of", "text"),
    "حدّ التأخّر المشتقّ": ("receivables.overdue_cutoff", "text"),
    "عدد الفواتير المتأخرة": ("receivables.overdue_invoice_count", "int"),
    "عملاء متأخرون": ("receivables.overdue_customers", "int"),
    "جارٍ — لم يحن استحقاقه": ("receivables.total_current", "egp"),
    "متأخر 1–30 يومًا": ("receivables.buckets.d1_30", "egp"),
    "متأخر 31–60 يومًا": ("receivables.buckets.d31_60", "egp"),
    "متأخر 61–90 يومًا": ("receivables.buckets.d61_90", "egp"),
    "متأخر 91–120 يومًا": ("receivables.buckets.d91_120", "egp"),
    "متأخر أكثر من 120 يومًا": ("receivables.buckets.d120p", "egp"),
}

# Expense totals are not a stored field: the app sums them across the eleven
# income statements in ``statements.expenses.by_statement``. Summed the same way
# here, so the capture reports what the screen reports.
EXPENSE_CATEGORIES = {
    "operating": "مصروفات تشغيلية",
    "admin": "مصروفات إدارية وعمومية",
    "selling": "مصروفات بيعية وتسويقية",
    "financing": "مصروفات بنكية وتمويلية",
}


def dig(obj, path: str):
    for part in path.split("."):
        if obj is None:
            return None
        if isinstance(obj, list):
            try:
                obj = obj[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            obj = obj.get(part) if isinstance(obj, dict) else None
    return obj


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_dash():
    """executive_dashboard/data.js is `window.DASH = {...};`."""
    try:
        txt = DASH_JS.read_text(encoding="utf-8")
        return json.loads(txt[txt.index("{"):txt.rindex("}") + 1].replace("<\\/", "</"))
    except (OSError, ValueError):
        return None


def expense_metrics(doc) -> dict:
    """Expense totals, summed across the statements the way the app sums them.

    A category the map below does not name still lands in the total — a fifth
    group appearing is a real change and must move a number, not be dropped
    quietly into the gap between this map and the data.
    """
    rows = dig(doc, "statements.expenses.by_statement")
    rows = rows if isinstance(rows, list) else []
    cats: dict = {key: None for key in EXPENSE_CATEGORIES}
    total = item_rows = None
    if rows:
        cats = {key: 0.0 for key in EXPENSE_CATEGORIES}
        for row in rows:
            for key, value in (row.get("categories") or {}).items():
                cats[key] = cats.get(key, 0.0) + (value or 0.0)
        total = sum(cats.values())
        item_rows = sum(len(row.get("expense_items") or []) for row in rows)

    out = {"إجمالي المصروفات": {"value": total, "kind": "egp"}}
    for key, label in EXPENSE_CATEGORIES.items():
        out[label] = {"value": cats.get(key), "kind": "egp"}
    out["سطور بنود المصروفات"] = {"value": item_rows, "kind": "int"}
    return out


def capture() -> dict:
    out, cache = {}, {}
    for label, (path, dotted, kind) in METRICS.items():
        if path not in cache:
            cache[path] = load_json(path)
        val = dig(cache[path], dotted)
        if kind == "count":
            val = len(val) if isinstance(val, list) else None
        out[label] = {"value": val, "kind": kind}
    out.update(expense_metrics(cache.get(MARGIN) or load_json(MARGIN)))
    dash = load_dash()
    for label, (dotted, kind) in DASH_METRICS.items():
        out[label] = {"value": dig(dash, dotted), "kind": kind}
    return out


def fmt(value, kind: str) -> str:
    if value is None:
        return "—"
    if kind == "egp":
        return f"{value:,.0f}"
    if kind == "pct":
        return f"{value:.2f}%"
    return f"{value:,.0f}" if isinstance(value, (int, float)) else str(value)


def delta(before, after, kind: str) -> str:
    if before is None and after is None:
        return "—"
    if before is None:
        return "جديد"
    if after is None:
        return "**اختفى**"
    if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
        # Text metrics (the two snapshot dates). No arithmetic, but they still
        # read down the same column as everything else, so an unchanged one says
        # so in the same words rather than trailing off into a dash.
        return "بلا تغيير" if before == after else "تغيّر"
    d = after - before
    if abs(d) < 1e-9:
        return "بلا تغيير"
    sign = "+" if d > 0 else "−"
    body = f"{sign}{abs(d):,.2f}" if kind == "pct" else f"{sign}{abs(d):,.0f}"
    if before:
        body += f"  ({sign}{abs(d) / abs(before) * 100:.1f}%)"
    return body


def diff(a: dict, b: dict) -> str:
    lines = ["### أثر البيانات الجديدة على الأرقام", "",
             "| المؤشر | قبل | بعد | الفرق |", "|---|---:|---:|---:|"]
    changed = 0
    for label in b:
        kind = b[label].get("kind", "int")
        before = (a.get(label) or {}).get("value")
        after = b[label].get("value")
        d = delta(before, after, kind)
        if d not in ("بلا تغيير", "—"):
            changed += 1
        lines.append(f"| {label} | {fmt(before, kind)} | {fmt(after, kind)} | {d} |")
    lines += ["", f"**{changed}** مؤشرًا تغيّر من أصل **{len(b)}**.", ""]
    if not changed:
        lines.append("لم تتغيّر أي أرقام — إعادة البناء متطابقة مع المُودَع.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[1] == "capture":
        Path(argv[2]).write_text(
            json.dumps(capture(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"captured {len(capture())} metrics -> {argv[2]}")
        return 0
    if len(argv) == 4 and argv[1] == "diff":
        a = load_json(Path(argv[2])) or {}
        b = load_json(Path(argv[3])) or {}
        print(diff(a, b))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
