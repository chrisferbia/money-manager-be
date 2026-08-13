---
stage: verified
updated: 2026-08-14
---

# Spec: Balances and Expense Reporting

## Overview
Read-only views over the transaction ledger: each account's current balance, and expense totals grouped by category. Nothing here is stored — both are computed on demand from `transactions` to avoid drift. The existing UI should show the same read-only information so users can see balances and reports without leaving the app.

## Dependencies
- 0001-account-master.md
- 0002-expense-categories.md
- 0003-transactions.md
- 0004-account-transfers.md

## Requirements
- [x] **R1** — An account's balance = sum of its `income` amounts − sum of its `expense` amounts − sum of its `transfer` amounts where it's the source + sum of its `transfer` amounts where it's the destination.
- [x] **R2** — `GET /accounts/{id}/balance` returns the computed balance for one account (404 if the account doesn't exist).
- [x] **R3** — `GET /accounts?include_balance=true` (extending **0001-account-master.md**'s list endpoint) returns every account with its computed balance alongside the existing fields.
- [x] **R4** — `GET /reports/expenses-by-category` returns, for each category that has at least one expense, the category and the sum of its expense amounts; supports optional `from`/`to` date filters on `occurred_at`.
- [x] **R5** — An account with no transactions has a balance of 0; a category with no expenses in the requested range is omitted from the report rather than shown as 0.
- [x] **R6** — `/ui/accounts` shows each account's current balance in the list view, using the same computed value as the balance API or `include_balance` list response.
- [x] **R7** — `/ui/reports/expenses-by-category` renders the grouped expense totals and provides `from`/`to` filters that limit the report to the selected `occurred_at` range.

## Acceptance Criteria
<!-- Each maps to one or more Requirements (verifies: R#). -->
- [x] **AC1** — For an account with a mix of income, expense, and transfers in/out, `GET /accounts/{id}/balance` returns the correct net total. _(verifies: R1, R2)_
- [x] **AC2** — A newly created account with no transactions has a balance of 0. _(verifies: R5)_
- [x] **AC3** — `GET /accounts?include_balance=true` returns balances matching what `GET /accounts/{id}/balance` reports for each account individually. _(verifies: R3)_
- [x] **AC4** — `GET /reports/expenses-by-category` sums expense amounts correctly per category and excludes categories with zero matching expenses. _(verifies: R4, R5)_
- [x] **AC5** — `GET /reports/expenses-by-category?from=...&to=...` restricts the sums to expenses whose `occurred_at` falls in range. _(verifies: R4)_
- [x] **AC6** — `/ui/accounts` shows balances that match the API for every listed account, including 0 for accounts with no transactions. _(verifies: R6, R1, R5)_
- [x] **AC7** — `/ui/reports/expenses-by-category` renders category totals and the visible date filters affect the displayed sums. _(verifies: R7, R4, R5)_

## Out of Scope
- Income-by-category or transfer reporting.
- Historical balance-as-of-date (only current balance is in scope).
- Charts/visualization — this is data endpoints only.

## Edge Cases
- Balance calculation must not double count a transfer on the source account side vs destination side — each transfer row affects exactly two accounts' balances via one row.
- Date filters on the report are inclusive of both `from` and `to`.

## Open Questions
- None currently.

## Verification Log
<!-- Appended by spec-verify, one row per evaluated item per round, newest last. -->
| Round | Date | Item | Result | Note |
|-------|------|------|--------|------|
| 1 | 2026-08-14 | AC1 | pass | Balance API returned correct net total with income, expense, and transfer. |
| 1 | 2026-08-14 | AC2 | pass | New account balance was 0. |
| 1 | 2026-08-14 | AC3 | pass | `include_balance` output matched the balance endpoint. |
| 1 | 2026-08-14 | AC4 | pass | Expense totals grouped correctly and omitted empty categories. |
| 1 | 2026-08-14 | AC5 | pass | Date range filter was inclusive and restricted the sums. |
| 1 | 2026-08-14 | AC6 | pass | `/ui/accounts` rendered balances and showed the same values as the API. |
| 1 | 2026-08-14 | AC7 | pass | `/ui/reports/expenses-by-category` rendered totals and filters affected output. |
