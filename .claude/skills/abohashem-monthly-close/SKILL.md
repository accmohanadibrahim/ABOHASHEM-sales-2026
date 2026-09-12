---
name: abohashem-monthly-close
description: >-
  The monthly data cycle for this repository (ABOHASHEM سلسلة أبو هاشم للحوم):
  new source files land — sales invoices, collections (تحصيلات), returns
  (مرتجعات), per-rep customer balance reports (مديونية العملاء), income
  statements (قائمة دخل) — and they have to be registered, read against their
  own printed totals, carried through the pipeline, rebuilt into the offline
  app, verified, documented and pushed. Use this skill whenever new data
  arrives for this repo or any figure in it has to move. It covers requests
  phrased as «تحديث البيانات», «اضافة ملفات شهر …», «حوّل الأقسام إلى لقطة
  <تاريخ>», «رصيد مديونية العملاء بتاريخ …», and the English equivalents —
  "update the data", "add August", "rebuild the app", "move everything to the
  N-M-YYYY snapshot". Use it for a SINGLE file as much as for a whole month,
  and use it when the question is "why is this number wrong?", because the
  answer is almost always which file was read. The words "close" or «إقفال»
  do not have to appear.
---

# ABOHASHEM — the monthly cycle

Every month the same thing happens: files are uploaded straight to `main` as
"Add files via upload" commits, and the numbers behind an offline app, an
executive dashboard and three written reports have to move with them — without
inventing anything.

The hard part is not the rebuild. It is **deciding which file is the truth**.
The same month often arrives twice in two different layouts on two different
bases, part-month files sit beside whole-month ones, a supplier report sits in
the middle of the customer reports, and a rep who filed last month does not file
this month. Every one of those has already happened here and every one of them
silently produces a plausible wrong number. That is why this skill leads with
registration and not with `python3`.

Work the six steps in order. Each ends in a gate; a gate that does not pass
stops the cycle rather than being worked around.

---

## 1. Register what arrived — before reading a byte of it

`executive_dashboard/src/config.py` is not a settings file. It is the decision
record: every source file is listed there **with its printed grand total and the
reason it is used or ignored**. Read it first, in full. It is the only place
that knows the traps, and it is where your answer goes too.

For every file that landed, write down three things and put them in `config.py`:

| | |
|---|---|
| **what it is** | sales invoices · collections · returns · per-rep balances · income statement |
| **which month it owns** | `"2026-08"`, or `None` for "every month no other file owns" |
| **its own printed total** | the grand total the document prints on itself |

The printed total is not decoration. Every parser in this repo reconciles
against it and **aborts** if it does not match to the piastre. A file with no
recorded total cannot be read, because nothing could then tell you a misread.

Then apply the rules that config.py already encodes — read
`references/sources.md` for the full list with the real examples. The six that
have actually bitten:

1. **Part-month vs whole-month.** Two July invoice files exist; one covers
   1–15 July. Reading it next to a full August makes every month-on-month
   figure wrong by construction. Take the whole-month file.
2. **Cumulative files overlap month files.** The cumulative collections run
   stops mid-month, so its last month is partial. A month-only file
   **supersedes** the cumulative file for the month it covers. Concatenating
   them double-counts half of July.
3. **A supplier report among the customer reports.** «مورين 3-9.pdf» is
   «حسابات الموردين» — money the company *owes*. It arrived in the same upload
   as the seven customer files. Including it inflates receivables by ~1.05M.
4. **A rep who did not file.** «محمود السيد» filed in July, not in September.
   His customers are reported as dropped. **No balance is carried forward** to
   fill the gap — a stale balance presented as current is a fabricated number.
5. **Two files, same month, different basis.** Both August collections files are
   real; one is cash receipts (سدادات), the other adds credit notes and old-return
   settlements. Every other month in the series is on the cash basis, so August
   stays on it. Mixing bases moves one month's collection-rate KPI and nothing
   else, which is exactly the kind of break nobody spots.
6. **The file name is the data.** The per-rep balance files are listed one by
   one, never globbed, because the filename *is* the official customer→rep
   assignment. A glob would guess it.

> **Gate:** every landed file appears in `config.py` with its total and its
> verdict — including the ones you decided *not* to read, and why. A file that
> is simply absent from config.py is indistinguishable from one nobody noticed.

## 2. Set the three dates — and derive the fourth

These are three different facts and conflating them has already produced a wrong
report:

| constant | what it means | where it comes from |
|---|---|---|
| `AS_OF_DATE` | when the money was counted | the date on the balance reports (`… 3-9.pdf` → `2026-09-03`) |
| `SNAPSHOT_DATE` | when this edition of the app was cut | the issue date you are publishing |
| invoice window end | last day of complete invoice data | the last **complete** month that arrived |

Re-dating receivables from the 3rd to the 4th would claim a count nobody made.
Keep them separate even when they are one day apart.

The overdue cutoff is **derived, never typed**: `config.overdue_cutoff()`
returns `AS_OF_DATE - NET_TERMS_DAYS`. A hand-written literal once sat there and
went stale — it said `2026-07-31` against an as-of of `2026-09-03`, granting 34
days of credit instead of the 30 the company gives.

> **Gate:** two checks, both cheap.
>
> ```bash
> # 1. the cutoff is still derived, not drifting.
> #    Load config.py BY PATH. Putting executive_dashboard/src on sys.path
> #    shadows the standard library — src/collections.py wins over stdlib
> #    `collections` and config.py then fails to import `re`.
> python3 -c "
> import importlib.util
> s = importlib.util.spec_from_file_location('cfg', 'executive_dashboard/src/config.py')
> c = importlib.util.module_from_spec(s); s.loader.exec_module(c)
> print(c.AS_OF_DATE, c.NET_TERMS_DAYS, c.overdue_cutoff())"
> # expected today: 2026-09-03 30 2026-08-04
>
> # 2. this round added no date literal outside config.py
> git diff -U0 -- '*.py' ':!executive_dashboard/src/config.py' | grep -n '^+.*20[0-9][0-9]-[0-9][0-9]'
> ```
>
> The second is scoped to **your own diff** on purpose. A blanket grep over the
> tree returns long-standing hits and trains you to skip the gate — for example
> `insights.py` falls back to a hard-coded `"2026-06"` focus month when the
> requested one is absent. That one predates this skill; leave it unless the
> owner asks, but do not add a second like it.

## 3. Read and reconcile

Run the parsers. Each one reconciles to the printed total recorded in step 1 and
aborts otherwise — so a clean run *is* the reconciliation.

If a file arrives in a **layout no parser knows** — as the August returns did
(one row per returned item instead of one row per credit note), and as the 2026
income statements did — do not force it through an existing parser and do not
fall back to flattened text. Read `references/new-shape.md`: read the page as
positioned words, take the group boundaries from the accountant's own totals,
and require three independent reconciliations before trusting a figure.

If a month cannot be reconciled, it ships with its totals and **no** line detail.
That is the existing policy for both the workbook and the PDF path: a missing
breakdown is honest, a plausible wrong one is not.

> **Gate:** every parser exits 0. No month is quietly dropped; a month that
> failed reconciliation is named in the run log and in the data-quality report.

## 4. Rebuild

```bash
.claude/skills/abohashem-monthly-close/scripts/rebuild.sh
```

Order matters at the end: `10_export_dashboard_data.py` writes the dashboard
payload, then `13_join_cost_margin.py` joins cost to sales, then
`14_income_statements.py` absorbs the income statements — the last two write the
profitability outputs the mobile app and the PDF page read. Stopping at step 10
leaves the dashboard complete and the profitability section empty.

The script wraps everything in a subshell with `set -e` inside it. This is
deliberate and is explained in `README.md`: without it an early script fails, its
old outputs stay on disk, the dashboards get built from mixed data, and the run
looks like it succeeded.

Dependencies install from the pinned `requirements.txt`. A newer `statsmodels`
than the pinned 0.14.6 shifts the VIF diagnostics and makes every rebuild look
like a data change when nothing changed.

## 5. Verify

```bash
.claude/skills/abohashem-monthly-close/scripts/verify.sh
```

It runs, and fails the cycle on any one of:

- `pytest -q` — the unit suite (112 at the time of writing)
- the same suite with `polars` stubbed out — CI installs only `flake8 pytest`,
  so a heavy import at module scope passes locally and breaks CI
- `node --test mobile/tests/mobile.test.js` (17)
- `mobile/tools/smoke_test.py` — boots the bundle in Chromium and walks all 23
  sections; a section that renders empty or throws fails
- `mobile/tools/test_exports.py` — opens the generated workbook with openpyxl
  (28 sheets), parses the CSV and the SVG, decodes the PNG
- three consecutive builds hashing identically — the build must be deterministic
  or "no change" cannot be distinguished from "changed back"
- `flake8 --select=E9,F63,F7,F82`

One red is the cycle not finished.

## 6. Document, then push

The figures reach a board report, so the written record moves with them:

- `reports/data_quality_report.md` — new coverage, new limits, anything that did
  not reconcile
- `reports/investor_executive_report.md` — a dated appendix, never an edit that
  silently restates an old number
- `data/cost/PROVENANCE.md` — when a cost or statement source changed
- `mobile/README.md` — when a section or an export sheet changed

Then commit, push to the working branch, and open a **draft** PR. Nothing is
merged automatically: `.github/workflows/rebuild-on-data.yml` also rebuilds on
upload and opens a PR carrying a before/after table of the headline figures from
`analysis/tools/kpi_snapshot.py`. A person approves the change in the numbers.

---

## Stop and ask

Do not resolve these alone. Each one has a defensible answer either way, and
each one silently changes a published figure:

- **Two files claim the same month with different totals.** Which basis is the
  series on? (See trap 5.)
- **A rep did not file this round.** Report dropped, or wait for the file?
- **A report of a different kind arrived in the batch** — suppliers, a
  statement instead of a receipts ledger.
- **A file covers half a month.**
- **A new expense line has no category decision.** `expense_categories.py`
  raises `UnknownExpenseItem` by design; there is no default bucket, and adding
  one is a decision, not a fix.
- **A figure the user quotes disagrees with the app.** Find which file each
  number came from before changing anything. The 2.28M-vs-2.94M discrepancy was
  a month filter narrowing a balance, not a parsing error.

## Rules that do not bend

Stated by the repo owner, and encoded in the tests:

- Never invent, estimate, silently correct, or infer a missing invoice, payment,
  cost, customer, product, KPI, balance or profit.
- **Never turn missing data into zero.** A month with no income statement shows
  no expense figure — not `0`. August 2026 is the live example.
- Never conceal a data-quality problem.
- If something cannot be verified from the source, say so explicitly instead of
  guessing.

Every figure on screen carries how it was obtained. The vocabulary and the
on-screen conventions are in `references/integrity.md`; how a number travels
from a source file to a section and an export sheet is in `references/payload.md`.

## Security — standing, unchanged

`mobile/dist/` contains customer names and balances, per-customer and per-rep
monthly profitability, overdue invoices by name, and a full year of company
expense lines (salaries, rents, loans, insurance, named lawyer fees).

**It is not published to any public hosting — GitHub Pages included — without an
explicit decision from the owner.** Do not set that up as a convenience.
