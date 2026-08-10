---
stage: draft
updated: 2026-08-10
---

# Spec: Account Transfers

## Overview
Lets the user move money between two of their own accounts as a single transfer record, using the `transactions` table and `transfer` type introduced in **0003-transactions.md**.

## Dependencies
- 0001-account-master.md
- 0003-transactions.md

## Requirements
- [ ] **R1** — `POST /transfers` creates a single `transactions` row with `type=transfer`, `account_id` = source account, `related_account_id` = destination account, `amount` > 0, no `category_id`.
- [ ] **R2** — Validation: `account_id` and `related_account_id` must both reference existing accounts and must differ; `amount` must be positive.
- [ ] **R3** — `GET /transactions` (from **0003-transactions.md**) includes transfer rows and exposes `related_account_id` in the response; filtering by `account_id` matches a transfer where that account is *either* the source or the destination.
- [ ] **R4** — `DELETE /transactions/{id}` (from **0003-transactions.md**) also works for transfer rows, fully reversing the transfer.
- [ ] **R5** — `PATCH /transactions/{id}` (from **0003-transactions.md**) applied to a transfer row allows updating `amount`, `description`, `occurred_at`; `related_account_id` and `account_id` are immutable after creation (consistent with `type` being immutable).

## Acceptance Criteria
<!-- Each maps to one or more Requirements (verifies: R#). -->
- [ ] **AC1** — Creating a valid transfer returns 201 with a transaction row of `type=transfer` showing both `account_id` and `related_account_id`. _(verifies: R1)_
- [ ] **AC2** — Transferring to the same account, a nonexistent account, or a non-positive amount returns a 4xx error and no row is inserted. _(verifies: R2)_
- [ ] **AC3** — `GET /transactions?account_id=X` includes a transfer where `X` is the destination, not just the source. _(verifies: R3)_
- [ ] **AC4** — Deleting a transfer transaction removes it like any other transaction. _(verifies: R4)_
- [ ] **AC5** — `PATCH` on a transfer rejects changes to `account_id`/`related_account_id`. _(verifies: R5)_

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
