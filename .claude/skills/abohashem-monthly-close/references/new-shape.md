# A file arrived in a layout nothing here parses

This happens perhaps twice a year and it is where wrong numbers get made. The
August returns came as one row per returned *item* instead of one row per credit
note; the 2026 income statements came as PDFs whose Arabic text layer is
ligature-decomposed. Both looked unreadable at first and both turned out to be
clean tables.

The method below is what `analysis/tools/extract_income_statements.py` does. Read
that file before writing a new parser — it is the worked example, and its module
docstring explains why each rule exists.

## 1. Never read the flat text

`page.get_text()` flattens the page into a stream, and on these documents the
stream is a lie:

- labels glue onto figures — `منظفات ومكافحة7870`
- reading order scrambles, so "the number after the label" is not the label's number
- in one document the group totals are emitted *after* the net-profit line

`page.get_text("words")` gives every word with its bounding box. Once the
coordinates are kept, every one of these documents is a plain table: group header
in its own left-hand column, item label in the middle, amount in one column,
percentage on the right. Nothing is inferred from reading order at all.

The same applies to the collections, returns and balance PDFs: `src/debt.py`,
`src/collections.py` and `src/invoice_pdf.py` are all geometric x-band parsers.
There is no flat-text parser in this repo and there should not be one.

## 2. Cluster rows by y-band, not by line

One logical row is routinely split across two very close y-lines — an amount
lands in one band and its label in the band above. Cluster words into bands with
a tolerance:

```python
BAND = 7.0     # points; rows within this are one logical row
```

and sort each band right-to-left.

## 3. Derive thresholds per document, never fix them

The first version of the PDF parser used a fixed `HEAD_X = 250` to tell a group
header from an item row. It read «مصاريف المكتب» and «مصاريف قرض المبادرة» as
group headers, because those documents sit at different origins.

Derive it instead:

```python
HEAD_GAP = 60.0
head_x = median(x of the item label starts) - HEAD_GAP
```

The same lesson in the workbook path: the six sheets start at B4, E5, G6, G7, I9
and G5. A positional rule reads a different line on every sheet. **Labels are the
only stable anchor.**

## 4. A number inside the label's own span is part of the name

«عربية 1639», «عربية 1642», «عربية 3782», «عربية 4195» are four different
vehicles. Treating every number as a figure collapses them into one «عربية».

```python
lo = min(label_x) - LABEL_NUM_GAP     # LABEL_NUM_GAP = 50.0
hi = max(label_x)
is_label_word = lo <= x < hi
```

The right-hand bound `hi` is not optional: without it a group total at x=371
beside a one-word header at x=53 is read as part of the label, and header
detection breaks in the other direction. Both halves of this rule were added to
fix a bug the other half caused.

## 5. Take the group's boundary from the accountant's own SUM

In the workbook, the items belonging to a group are the cells the accountant's
own `SUM()` range covers — `_cells_in_formula()` reads the formula and follows
it. That is a fact about the document; any other rule is a guess about layout.

## 6. Require three independent reconciliations

This is what makes reading these documents defensible at all. The figures are
not trusted because the parser looks careful; they are trusted because the
document states three things that must agree:

1. **each group's own printed total** equals the sum of its items
2. **the sum of the groups** equals `gross_profit − net_profit`
3. **each item's printed percentage** of net sales equals `amount ÷ net_sales`

A month that fails any of them ships with its totals and **no line detail** —
the same output as before the parser existed, but now reached by measurement
rather than by blanket policy.

Look at `pdf_expense_items()` for the shape:

```python
pool = [it for it in mine if it["amount"]]          # zero rows excluded: they make
fits = [drop for drop in _subsets(pool, 3)          # the subset fit ambiguous
        if any(close(got - sum(d["amount"] for d in drop), w) for w in wants)]
if len(fits) != 1:
    return None, [], []                             # ambiguous is a failure, not a pick
```

**A unique fit or nothing.** If two different subsets would both reconcile, the
document has not told you which is right, and choosing is inventing.

## 7. Rows outside the totals are shown, never added

Sixteen rows across these statements are printed in the document but summed by no
group total: «مواصلات اسوان», «فتيس فاستر», «مرتبات انتاج والمصنع», two June loan
lines, and ten in 2025 — 135,351 EGP in all.

They are **not** an extraction failure and adding them is not a fix. It is proved
arithmetically: the statement's own total reconciles *without* them. They are not
in total expenses and not in the printed net profit, so folding them in would
make the app disagree with the document.

They go into `expense_rows_outside_totals` and are displayed on their own card,
labelled, and added to nothing.

## 8. Spell out every alias; never write a general de-ligaturizer

The 2026 text is decomposed in ways that are easy to pattern-match and dangerous
to generalise: `مرصوفات` `بدالت` `محاىم` `حكوىم` `الفاسير` `فالتر` `مواصالت`
`تامير` `االشهار` `صافن`.

`analysis/lib/expense_aliases.py` lists all 43 spellings explicitly, keyed by
`(group, raw label)`. A general normaliser would work today and silently merge
two genuinely different lines tomorrow — and nothing would flag it.

Anything with no alias passes through with its literal spelling. The raw label
stays beside the canonical one everywhere, on screen and in the export.

## 9. No default bucket

A new expense line with no category decision raises `UnknownExpenseItem` and
stops the run. There is no fallback bucket, and adding one is a decision for the
owner, not a fix for the error.

The decision file `analysis/lib/expense_categories.py` is written by hand — every
line a human decision — and `analysis/tests/test_expense_items.py` re-derives the
whole map from the four-category statements and fails if the file disagrees. It
also fails on a decision that never applies, because a stale decision is one
nobody can check.

## When you have finished

Add the new parser's printed-total reconciliation to `config.py` alongside the
file (see `sources.md`), add a test that reconciles it against the source, and
record the new shape in `reports/data_quality_report.md` — including what the new
reading does *not* cover.
