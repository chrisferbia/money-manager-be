---
stage: verified
updated: 2026-08-14
---

# Spec: Account Transfers

## Overview
Lets the user move money between two of their own accounts as a single transfer record, using the `transactions` table and `transfer` type introduced in **0003-transactions.md**. The existing `/ui/transactions` screen should surface transfer creation and display without requiring a separate UI section.

## Dependencies
- 0001-account-master.md
- 0003-transactions.md

## Requirements
- [x] **R1** — `POST /transfers` creates a single `transactions` row with `type=transfer`, `account_id` = source account, `related_account_id` = destination account, `amount` > 0, no `category_id`.
- [x] **R2** — Validation: `account_id` and `related_account_id` must both reference existing accounts and must differ; `amount` must be positive.
- [x] **R3** — `GET /transactions` (from **0003-transactions.md**) includes transfer rows and exposes `related_account_id` in the response; filtering by `account_id` matches a transfer where that account is *either* the source or the destination.
- [x] **R4** — `DELETE /transactions/{id}` (from **0003-transactions.md**) also works for transfer rows, fully reversing the transfer.
- [x] **R5** — `PATCH /transactions/{id}` (from **0003-transactions.md**) applied to a transfer row allows updating `amount`, `description`, `occurred_at`; `related_account_id` and `account_id` are immutable after creation (consistent with `type` being immutable).
- [x] **R6** — `/ui/transactions` includes a transfer creation form or equivalent affordance that captures source account, destination account, amount, optional description, and occurred_at, and enforces the same validation rules as `POST /transfers`.
- [x] **R7** — Transfer rows are rendered in the transaction list and edit view in a way that clearly distinguishes source and destination accounts; the UI does not present transfer account fields as editable after creation.

## Acceptance Criteria
<!-- Each maps to one or more Requirements (verifies: R#). -->
- [x] **AC1** — Creating a valid transfer returns 201 with a transaction row of `type=transfer` showing both `account_id` and `related_account_id`. _(verifies: R1)_
- [x] **AC2** — Transferring to the same account, a nonexistent account, or a non-positive amount returns a 4xx error and no row is inserted. _(verifies: R2)_
- [x] **AC3** — `GET /transactions?account_id=X` includes a transfer where `X` is the destination, not just the source. _(verifies: R3)_
- [x] **AC4** — Deleting a transfer transaction removes it like any other transaction. _(verifies: R4)_
- [x] **AC5** — `PATCH` on a transfer rejects changes to `account_id`/`related_account_id`. _(verifies: R5)_
- [x] **AC6** — A user can create a valid transfer from `/ui/transactions` and see it appear in the list with both accounts visible. _(verifies: R6, R3, R1)_
- [x] **AC7** — Invalid transfer submission from the UI shows a visible error and preserves the entered values. _(verifies: R2, R6)_
- [x] **AC8** — Transfer rows in the UI remain unambiguous about source versus destination, and the edit form does not allow changing either account. _(verifies: R7, R5)_

## Out of Scope
- Transfer fees or currency conversion.
- Scheduled/recurring transfers.

## Edge Cases
- Deleting either account involved in a transfer is blocked by the existing R7 guard in **0003-transactions.md** (transfers count as referencing transactions).

## Open Questions
- None currently.

## Verification Log
<!-- Appended by spec-verify, one row per evaluated item per round, newest last. -->
| Round | Date | Item | Result | Note |
|-------|------|------|--------|------|
| 1 | 2026-08-14 | AC1 | pass | `POST /transfers` returns a transfer row with source and destination accounts. |
| 1 | 2026-08-14 | AC2 | pass | Invalid transfer payloads are rejected with 4xx/422 and no row is created. |
| 1 | 2026-08-14 | AC3 | pass | Destination account filtering returns the transfer. |
| 1 | 2026-08-14 | AC4 | pass | Deleting a transfer removes it and subsequent GET returns 404. |
| 1 | 2026-08-14 | AC5 | pass | Transfer patch updates allowed fields and rejects account changes. |
| 1 | 2026-08-14 | AC6 | pass | `/ui/transactions` can create and render transfers. |
| 1 | 2026-08-14 | AC7 | pass | Invalid UI transfer submission re-renders the form with an error and preserved input. |
| 1 | 2026-08-14 | AC8 | pass | Transfer UI distinguishes source/destination and hides account-field edits. |
