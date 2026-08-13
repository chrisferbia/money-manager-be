---
stage: tested
updated: 2026-08-13
---

# Spec: Transactions (Income & Expense)

## Overview
Lets the user record money moving into (income) or out of (expense) an account, and list/filter that history. Expense transactions must be tagged with a category from **0002-expense-categories.md**; income transactions are not categorized. This spec also retroactively adds the delete-guards on `accounts` and `categories` promised in specs 0001/0002, since the `transactions` table they reference is created here.

## Dependencies
- 0001-account-master.md
- 0002-expense-categories.md

## Requirements
- [ ] **R1** — Add a `transactions` table to the D1 schema: `id` (integer, autoincrement PK), `type` (text, one of `income`/`expense`/`transfer` — this spec only creates rows with `income`/`expense`; `transfer` is used starting in **0004-account-transfers.md**), `account_id` (integer, required, FK → `accounts.id`), `category_id` (integer, nullable, FK → `categories.id`), `related_account_id` (integer, nullable — unused until 0004), `amount` (integer, required, > 0, stored in minor currency units e.g. cents), `description` (text, nullable), `occurred_at` (text, required, ISO8601, defaults to now if omitted), `created_at` (text, default current timestamp).
- [ ] **R2** — `POST /transactions` creates an income or expense transaction. `type` must be `income` or `expense`; `account_id` must reference an existing account; `amount` must be a positive number; for `type=expense`, `category_id` is required and must reference an existing category; for `type=income`, `category_id` must be omitted/null.
- [ ] **R3** — `GET /transactions` lists transactions, filterable by `account_id`, `category_id`, `type`, and an `occurred_at` date range (`from`/`to`), newest first.
- [ ] **R4** — `GET /transactions/{id}` returns a single transaction or 404.
- [ ] **R5** — `PATCH /transactions/{id}` updates a transaction's mutable fields (`amount`, `category_id`, `description`, `occurred_at`); the same type/category validation as create applies; `type` and `account_id` are immutable after creation.
- [ ] **R6** — `DELETE /transactions/{id}` removes a transaction; returns 404 if not found.
- [ ] **R7** — `DELETE /accounts/{id}` (from **0001-account-master.md**) now returns a 409 if any transaction references that account.
- [ ] **R8** — `DELETE /categories/{id}` (from **0002-expense-categories.md**) now returns a 409 if any expense transaction references that category.

## Acceptance Criteria
<!-- Each maps to one or more Requirements (verifies: R#). -->
- [ ] **AC1** — Creating a valid income transaction (no category) returns 201 with the created row. _(verifies: R1, R2)_
- [ ] **AC2** — Creating a valid expense transaction with a valid `category_id` returns 201 with the created row. _(verifies: R1, R2)_
- [ ] **AC3** — Creating an expense without `category_id`, an income with `category_id` set, an amount ≤ 0, or a nonexistent `account_id`/`category_id` all return a 4xx error and no row is inserted. _(verifies: R2)_
- [ ] **AC4** — `GET /transactions?account_id=X` returns only that account's transactions; combining `category_id`, `type`, and date-range filters narrows results correctly; results are ordered newest-first. _(verifies: R3)_
- [ ] **AC5** — `GET /transactions/{id}` returns the matching transaction, or 404 for an unknown id. _(verifies: R4)_
- [ ] **AC6** — `PATCH /transactions/{id}` updates allowed fields and re-validates category/type rules; attempts to change `type` or `account_id` are rejected. _(verifies: R5)_
- [ ] **AC7** — `DELETE /transactions/{id}` removes the row, and a subsequent `GET /transactions/{id}` returns 404. _(verifies: R6)_
- [ ] **AC8** — Deleting an account that has at least one transaction returns 409 and the account is not deleted. _(verifies: R7)_
- [ ] **AC9** — Deleting a category referenced by at least one expense transaction returns 409 and the category is not deleted. _(verifies: R8)_

## Out of Scope
- Transfers (`type=transfer`, `related_account_id`) — see **0004-account-transfers.md**.
- Account balances and expense-by-category reports — see **0005-balances-and-reporting.md**.
- Recurring/scheduled transactions, attachments/receipts, multi-currency.

## Edge Cases
- `amount` of 0 or negative is rejected; amount is an integer (minor units), not a float, to avoid rounding errors.
- Malformed or missing `occurred_at` defaults to the current time rather than erroring.
- Filtering by a `category_id` that has no expenses returns an empty list, not an error.

## Open Questions
- None currently.

## Verification Log
<!-- Appended by spec-verify, one row per evaluated item per round, newest last. -->
| Round | Date | Item | Result | Note |
|-------|------|------|--------|------|
