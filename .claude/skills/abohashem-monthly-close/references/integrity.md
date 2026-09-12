# Saying how a number was obtained

The repo owner's standing rules, and the conventions this repo built to keep
them. These are not aspirations — most of them are enforced by a test, and the
ones that are not are enforced by a card on the screen.

> Never invent, estimate, silently correct, or infer missing invoices, payments,
> costs, customers, products, KPIs, balances, or profits.
> Never convert missing data into zero.
> Never conceal a data-quality problem.
> If something cannot be verified from the available source, state that
> explicitly instead of guessing.

## Absent is not zero, and it is not last month either

Three separate states, three different renderings, never collapsed:

| state | what the app shows |
|---|---|
| measured | the figure |
| absent | no figure, and a named reason |
| estimated / allocated | the figure, labelled, with the method |

August 2026 has no income statement. It shows **no expense figure** — not `0`,
not a carried-forward July, not an average. `mobile/tools/smoke_test.py` asserts
that 2026-08 is absent from the expense payload, so a future change that
back-fills it fails the build.

The same rule in its other form: a rep who did not file this round has his
customers reported as dropped. A stale balance presented as current is as
fabricated as an invented one.

## The basis vocabulary

Every expense line carries **how it got its category**, on screen and in the
export. Four values, and they are claims about the document:

| basis | meaning | rows |
|---|---|---|
| `stated` | the statement itself declared the category | 223 |
| `mapped` | the four-category statements put this same name in exactly one category | 111 |
| `unsplit` | they put it in two, and the older statement did not split it | 8 |
| `as_filed` | the four-category statements do not carry it at all — left where it was filed | 18 |

`stated` is the strict one: a statement that printed three groups cannot state a
category it never named, and `test_stated_categories_come_only_from_the_statements_that_state_them`
fails if a reading is ever relabelled as a measurement.

`unsplit` is the honest limit, named rather than smoothed: «ايجارات» is one line
in the eight earlier statements and two (operating + a smaller administrative
one) in the later ones. Splitting it needs a ratio nobody measured; moving it
whole into a category most of it does not belong to is worse. It stays where it
was filed, flagged — so the administrative category is **higher** and the
operating one **lower** in those eight statements, and the reports say so.

## Decision files are re-derived, not trusted

`analysis/lib/expense_categories.py` is written by hand, every line a human
decision — and that is exactly why a test re-derives the whole map from the
four-category statements and fails if the file disagrees. The same test fails on
a **decision that never applies**, because a stale decision is one nobody can
check.

`classify()` raises `UnknownExpenseItem` for an administrative line it has no
decision for. There is no default bucket. Adding one would turn every future
unclassified line into a silent guess.

## Show the map, not just the result

A reading that lives only in a Python file is invisible to the person reading the
workbook. So:

- the 43 raw spellings sit beside their canonical names, on screen and in the
  `x_map` export sheet
- the category decisions are a table in the app and a sheet in the workbook
- the 16 rows printed outside any group total get their own card: displayed,
  labelled, **added to nothing** — and their exclusion is proved arithmetically,
  because the statement's own total reconciles without them
- a «ما لا يتوفّر» card names what the section does *not* cover

## Three dates, never one

`AS_OF_DATE` (when the money was counted) · `SNAPSHOT_DATE` (when this edition
was cut) · the invoice window end. Re-dating receivables by a single day claims a
count nobody made.

And the overdue cutoff is derived from `AS_OF_DATE − NET_TERMS_DAYS`, never
typed. The hand-written literal that used to sit there granted 34 days of credit
instead of 30 because nobody updated it with the snapshot.

## Quantities that carry no period

A balance is a point-in-time fact. It has no month, so selecting a month must not
shrink it — that bug made the debt read 2.28M when it was 2.94M. Sections whose
quantities are period-less are listed unfilterable; see `payload.md`.

## When a change supersedes old output

Say so plainly, and name what has to be rebuilt rather than reused. A corrected
dataset does not quietly coexist with the rankings that were built on the old one.

## Where this overlaps `finance-data-integrity-gate`

That installed skill is the general pre-analysis gate for freshly uploaded
financial data — parse checks, line-item arithmetic, unit discipline, assumption
registers. Use it when data arrives from **outside** this repo's pipeline.

This page is narrower and repo-specific: it is the vocabulary and the on-screen
conventions this codebase already enforces in tests. Where they agree, follow
either. Where this page is more specific, it wins, because a test here depends
on it.
