# How a number gets from a source file to the screen

Four hops. When a figure is wrong on screen, walk them in order — the fault is
almost always at hop 1 (which file was read), and almost never at hop 4.

```
source file  →  parser  →  data/processed/*.json + data.js  →  app section + export sheet
```

## Hop 1 — source → parser

Registered in `executive_dashboard/src/config.py`; see `sources.md`. Each parser
reconciles to the file's printed total and aborts otherwise.

The one place this hop forks: a **PDF sales-invoice month** is read by two
consumers. `executive_dashboard/build.py` picks it up from `config.py` alone,
while the analysis pipeline reads only the months listed in
`analysis/01_parse_invoices.py`'s `PDF_MONTHS` (by constant name — the path is
still written once). Register in one and not the other and the two sides disagree
with no error anywhere: the dashboard's invoice figures move, the app's do not.
`sources.md` carries the gate that catches it.

## Hop 2 — parser → payloads

Three payloads feed the offline app, and they are not interchangeable:

| payload | written by | carries |
|---|---|---|
| `dashboards/data.js` → `window.DASH_DATA` | `analysis/10_export_dashboard_data.py` | the 18-month aggregates: sales, customers, brands, forecast, quality |
| `executive_dashboard/data.js` → `window.DASH` | `executive_dashboard/build.py` | invoice-level detail, receivables, collections, aging |
| `data/processed/margin_dashboard.json` → `window.DASH_MARGIN` | `analysis/13_join_cost_margin.py` + `14_income_statements.py` | profitability, income statements, expenses |

Pipeline order matters here and only here: 10 writes the dashboard payload, then
13 joins cost to sales, then 14 absorbs the statements. Stop at 10 and the
dashboard is complete while the profitability and expense sections are empty.

Two files share the name `income_statements.json` and they are not the same thing:

| path | what it is |
|---|---|
| `data/cost/income_statements.json` | the **vendored extract** — written by `analysis/tools/extract_income_statements.py`, run **by hand** against the costing repo (`--repo ../Abohashem`). Not a pipeline step. |
| `data/processed/income_statements.json` | a pipeline **output** of `analysis/14_income_statements.py`, which reads the file above |

The vendoring pattern — parse and validate there, commit the reviewable JSON here,
leave the binary sources in `hannopo1/Abohashem` — is the same one
`data/cost/model_rows.json` uses. Provenance, including the source commit, is in
`data/cost/PROVENANCE.md`, and it has to be updated when the extract is re-run.

## Hop 3 — payload → section

`mobile/build_standalone.py` inlines the modules in this order, and the order is
load-bearing because each defines a namespace the next one uses:

```
dash-tokens.js  (T)  design tokens, section inventory
dash-agg.js     (A)  aggregation helpers
repo-adapter.js (R)  SECTIONS, KPI builders, filters over window.DASH_DATA
dash-aging.js   (G)  due dates and aging over window.DASH        → state.AG
dash-margin.js  (M)  profitability + expenses over window.DASH_MARGIN
dash-charts.js  (C)  ECharts wiring
dash-export.js  (X)  CSV / XLSX / PNG / SVG / PDF
dash-app.js          the React app: nav, sections, filters
```

The section list is assembled at runtime, not hard-coded:

```js
const list = (R ? R.SECTIONS : [])
  .concat(M.has()     ? [M.SECTION]     : [])   // الربحية
  .concat(M.hasExp && M.hasExp() ? [M.SECTION_EXP] : []);  // المصروفات
```

So a section **disappears when its payload is absent** rather than rendering
zeros. That is the design: `M.has()` and `M.hasExp()` are the honesty gates.
`mobile/tools/smoke_test.py` asserts the resulting count (23 today) so a section
that silently vanishes fails the build.

Filters do not apply to every section. `R.UNFILTERABLE` lists the repo-side ones
(`fin`, `forecast`, `quality`) and the app adds `margin` and `expenses`. Note the
nav key of a repo section is **prefixed** (`r:fin`), so match against the bare
section id, not `st.section` — matching the prefixed key silently never fires,
which is exactly the bug that once hid the "filters do not apply here" notice.

## Hop 4 — section → export sheet

`dash-export.js` builds 28 sheets. The rule that keeps them honest: **a reading
that is invisible in the workbook is a reading nobody can check.** So the item
sheet carries the original spellings and the basis of every category, and two
sheets carry the maps themselves:

| id | sheet |
|---|---|
| `x_month` | المصروفات الشهرية — four category columns, plus the basis of each month |
| `x_cat` | المصروفات حسب الفئة |
| `x_item` | المصروفات لكل بند — one column per statement, raw spellings, note |
| `x_map` | قرارات الفئات ومرادفات البنود — the decision table and the 43 aliases |

`mobile/tools/test_exports.py` opens the generated workbook with openpyxl and
counts them, so adding a section without its sheet fails.

## When a figure on screen is wrong

Work backwards, and suspect hop 1 first:

1. **Which file did it come from?** Check `config.py`. The 2.28M-vs-2.94M debt
   discrepancy was not a parsing error — a month filter was narrowing a balance
   that has no month. A balance is a point-in-time fact; it does not belong to a
   month and must not shrink when one is selected.
2. **Did a reconciliation pass?** A passing build means every printed total
   matched. If the figure is wrong *and* the totals reconcile, the wrong file was
   read — not the file wrongly.
3. **Is it a filtered view of an unfilterable quantity?** See above.
4. Only then look at the section code.

## The ad-hoc section is different, and that is deliberate

`mobile/src/dash-adhoc.js` (namespace `Q`) reads `window.DASH.lines` **directly**
and carries its own period and filters, instead of taking the filtered context
every other section receives. That is not an oversight: a query builder whose
scope is quietly narrowed by the global month chip reports a number the reader
cannot account for.

Consequences for a close round:

* It needs no wiring when a month lands. New lines flow into it because it reads
  the same `lines` array — there is no per-section registration of months.
* Its four rules are data-shaped, so **re-check them when the extract changes**:
  customers group by `customer_code` (84 codes carry several name spellings),
  `boxes` null is not zero (232 weight-sold lines), bonus is out of revenue by
  default (415 lines, 24,305 units, 740.00 EGP), and both quantities accumulate
  side by side. `mobile/tests/mobile.test.js` pins all four on a fixture, and
  `mobile/tools/test_adhoc.py` re-checks them against the real bundle.
* **There is no customer type in any payload.** If a future extract adds one,
  it belongs in `Q.DIMS` and `Q.FILTERS` as a real dimension; until then the
  ABC/XYZ classes stand in, under a label that says they are derived. Do not
  invent a type from city, rep, or revenue band.

## Adding a section

Whatever else you do, the three that are always missed:

- an `M.hasX()`-style gate so it vanishes rather than showing zeros
- its export sheet in `dash-export.js`
- the new counts in `mobile/tools/smoke_test.py` and `mobile/tools/test_exports.py`,
  plus its headline figure in `analysis/tools/kpi_snapshot.py` so the rebuild PR
  diffs it
