# A new file arrived — where it goes and what it can cost you

Read this with `executive_dashboard/src/config.py` open. Everything below is
already recorded there against the file it applies to; this page is the map, not
a second source of truth. **If the two ever disagree, config.py wins and this
page is stale — fix it.**

## The five kinds of file, and who parses each

| kind | Arabic on the file | parser | reconciles against |
|---|---|---|---|
| sales invoices | فواتير المبيعات | `src/invoice_pdf.py` (PDF, July 2026→) · `src/load.py` (pre-converted `.md`, →June 2026) | each invoice's own printed total, Σ lines vs header |
| collections | تحصيلات / سدادات العملاء | `src/collections.py` | the file's printed grand total, exactly |
| returns | مرتجعات / ارتجاعات العملاء | `src/collections.py` (credit-note layout) · itemised layout has its own band set | the file's printed grand total, exactly |
| customer balances | تقرير عن حسابات العملاء | `src/debt.py` | per-rep totals; `AR_SNAPSHOT_FILES` is a hand-listed set |
| income statements | قائمة دخل تفصيلى | `analysis/tools/extract_income_statements.py` | three independent checks — see `new-shape.md` |

Sales invoices from July 2026 onwards arrive as native PDFs, one invoice per
page, with a real text layer. Before that they were delivered as pre-converted
markdown. Both paths still run; neither is retired.

## Register the file before you read it

Add it to the right list in `config.py` with **its printed grand total**, and
with a comment saying why it is used — or why it is not. Both halves matter. A
file that is simply absent from config.py cannot be told apart from one nobody
noticed, and the next session will re-derive the same decision from scratch or
get it wrong.

The collection and return lists take a third field that carries the rule:

```python
SRC_COLLECTIONS: list[tuple[Path, str | None, float]] = [
    (REPO_ROOT / "…من 1-1-2026 الى 18-7-2026.pdf", None,      22_177_149.68),
    (REPO_ROOT / "…حتى تاريخ 30-7-2026.pdf",        "2026-07",  4_031_541.00),
    (REPO_ROOT / "…شهر 8.pdf",                      "2026-08",  4_022_295.50),
]
```

`None` means "every month no other entry owns". A month string means "this file
owns that month". Entries are ordered oldest-first and **later entries win**.

## The traps, with the real case each time

### 1. Part-month beside whole-month

Two July invoice files sit in the repo. `فواتير المبيعات من 1_7_2026الى 15_7_2026.pdf`
covers half the month and is a strict **prefix** of `فواتير المبيعات خلال شهر 7.pdf`.

Read the part-month one beside a complete August and every month-on-month figure
in the app is wrong by construction — not by a rounding error, by half a month of
revenue. The whole-month file is the one wired up; the part-month file is left in
the repo, unused, and said to be unused in config.py.

**Rule:** a file whose name carries a day range that is not the whole month is
suspect until you have checked whether a whole-month version also arrived.

### 2. A cumulative file overlaps the month files

The collections ledger arrives as one cumulative run plus later month-only files,
and they **overlap**: the cumulative run stops on 18 July, so its July is
partial. The month file is the same ledger re-run after the month closed.

Concatenate them and the first half of July is counted twice. Hence the
supersede rule above: the month-only file wins for its month, the cumulative one
covers everything else.

**Rule:** never `+` two receipt or return files. Decide month ownership.

### 3. A supplier report inside the customer batch

`مورين 3-9.pdf` arrived in the same upload as the seven customer balance files
and looks exactly like them. It is «حسابات الموردين» — **supplier** accounts,
about 1.05M of money the company *owes*.

Adding it to `AR_SNAPSHOT_FILES` inflates customer receivables by that much and
nothing in the pipeline would complain: the parser handles the layout fine, the
per-rep total reconciles fine, and the app shows a receivable that does not
exist.

**Rule:** open each balance file and confirm the report title says عملاء, not
موردين, before listing it.

### 4. A rep who did not file

`محمود السيد` filed on 16 July and not on 3 September. His customers are reported
as **dropped**, and no balance is carried forward from July to fill the hole.

Carrying a July balance into a September snapshot presents a stale number as a
current count. That is the "never turn missing data into zero" rule in its other
form: never turn missing data into last month's number either.

**Rule:** a rep missing from this round is named in the data-quality report, not
back-filled.

### 5. Two files, same month, different basis

Two August collections reports arrived:

| file | total | basis |
|---|---|---|
| `تحصيلات العملاء شهر 8.pdf` | 4,022,295.50 | cash receipts (سدادات) |
| `تحصيلات العملاء شهر 8 سنة 2026.pdf` | 4,156,517.75 | receipts **+** credit notes (إشعار خصم) and old-return settlements |

The second is not a corrected version of the first. It is a different basis —
134,222.25 of it is not cash received. Every other month in this dataset is on
the cash basis, so August stays on it; the alternative is recorded in
`SRC_COLLECTIONS_AUG_ALT` and not used.

Switching basis for one month moves that month's collection-rate KPI and nothing
around it, which is precisely the kind of break that survives review.

**Rule:** when two files claim one month, ask which basis the series is on —
and then stop and ask the owner, per SKILL.md.

### 6. The filename is the data

`AR_SNAPSHOT_FILES` pairs each PDF with a rep name by hand:

```python
(REPO_ROOT / "بشرى 3-9.pdf", "محمد بشرى"),
```

It is not globbed, because the filename *is* the official customer→rep
assignment — and the filename spelling and the rep's full name differ. A glob
would guess the mapping and would silently pick up file 3 above.

**Rule:** list balance files one by one, with the rep stated.

## After registering

Nothing else in the pipeline needs a path. Every downstream script reads
`config.py` or the processed outputs. If you find yourself typing a filename
into a second place, that is the bug.

Then run the parsers (step 3 of SKILL.md) and let the reconciliations speak.
A file registered with the wrong total aborts the build — which is the point.
