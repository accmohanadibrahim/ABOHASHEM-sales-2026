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

`محمود السيد` filed on 16 July and not on 3 September.

**Do this:** leave his file out of `AR_SNAPSHOT_FILES` entirely, and name his
customers in `reports/data_quality_report.md` as missing from the snapshot.

**Do not** carry his July balance forward, and do not keep it with its own older
date beside the others. The second one looks like the careful option and is
worse: a snapshot holding balances struck on two different days makes
"إجمالي المديونية" the sum of two different moments — a figure that describes no
day at all, while still presenting itself as today's. Dropping him leaves a hole
you can see and say out loud; tagging him hides one inside a total.

That is "never turn missing data into zero" in its other form: never turn missing
data into last month's number either.

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

## One path, two registrations

The path is written once, in `config.py`. But a **PDF sales-invoice month** has a
second registration, and missing it is silent:
`analysis/01_parse_invoices.py` carries the list of months to read, by constant
name:

```python
# The PDF months, in the shared parser's terms: (config attribute, source tag).
# Adding a month means adding its path to executive_dashboard/src/config.py and
# one line here — never a new parser.
PDF_MONTHS = [("SRC_JULY_PDF", "july_2026"), ("SRC_AUGUST_PDF", "august_2026")]
```

By **constant name**, not by path — the path still lives in exactly one place.
Add the line, and nothing else: the parser is shared with the dashboard
(`executive_dashboard/src/invoice_pdf.py`) and a new month never needs a new one.

This was found the expensive way. A month registered in `config.py` and missing
from `PDF_MONTHS` produces no error at all: the dashboard reads the new invoices,
the analysis pipeline does not, every build stays green, and revenue, customer
count and month count all silently keep last month's values.

> **Gate — run it, do not reason about it.** Silent on a correct tree; on a tree
> with the month registered once it names the constant.
>
> ```bash
> python3 - <<'PY'
> import importlib.util, re, pathlib
> s = importlib.util.spec_from_file_location('cfg', 'executive_dashboard/src/config.py')
> c = importlib.util.module_from_spec(s); s.loader.exec_module(c)
> months = set(re.findall(r'\("(SRC_\w+)"',
>     pathlib.Path('analysis/01_parse_invoices.py').read_text(encoding='utf-8')))
> missing = [n for n in dir(c) if re.fullmatch(r'SRC_\w+_PDF', n) and n not in months]
> print("NOT READ BY THE PIPELINE:", missing or "none")
> PY
> ```

Everything else really does read `config.py` or the processed outputs. Collections,
returns and balance files are registered once, in their lists, and no second edit.

Then run the parsers (step 3 of SKILL.md) and let the reconciliations speak.
A file registered with the wrong total aborts the build — which is the point.
