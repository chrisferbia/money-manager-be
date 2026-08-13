---
stage: tested
updated: 2026-08-13
---

# Spec: Expense Categories

## Overview
Lets the user define categories (e.g. "Groceries", "Transport") to group expense transactions for later reporting.

## Requirements
- [ ] **R1** — Add a `categories` table to the D1 schema: `id` (integer, autoincrement primary key), `name` (text, required, unique), `created_at` (text, default current timestamp).
- [ ] **R2** — `POST /categories` creates a category given `name`; rejects blank or duplicate `name`.
- [ ] **R3** — `GET /categories` lists all categories.
- [ ] **R4** — `GET /categories/{id}` returns a single category or 404 if not found.
- [ ] **R5** — `PATCH /categories/{id}` renames a category; same validation as create.
- [ ] **R6** — `DELETE /categories/{id}` removes a category; returns 404 if not found. (Deletion is blocked once expense transactions reference it, per **0003-transactions.md**.)

## Acceptance Criteria
<!-- Each maps to one or more Requirements (verifies: R#). -->
- [ ] **AC1** — Creating a category with a valid name returns 201 with the created category and an `id`. _(verifies: R1, R2)_
- [ ] **AC2** — Creating a category with a blank or duplicate name returns a 4xx error and no row is inserted. _(verifies: R2)_
- [ ] **AC3** — `GET /categories` returns all created categories. _(verifies: R3)_
- [ ] **AC4** — `GET /categories/{id}` returns the matching category, or 404 for an unknown id. _(verifies: R4)_
- [ ] **AC5** — `PATCH /categories/{id}` persists the new name; blank/duplicate renames are rejected. _(verifies: R5)_
- [ ] **AC6** — `DELETE /categories/{id}` removes the category, and a subsequent `GET /categories/{id}` returns 404. _(verifies: R6)_

## Out of Scope
- Applying categories to income transactions (income is uncategorized per the agreed data model — see **0003-transactions.md**).
- Blocking deletion of categories referenced by expenses (needs the `transactions` table — see **0003-transactions.md**).
- Nested/hierarchical categories.

## Edge Cases
- Duplicate category name (case-sensitive exact match) is rejected.

## Open Questions
- None currently.

## Verification Log
<!-- Appended by spec-verify, one row per evaluated item per round, newest last. -->
| Round | Date | Item | Result | Note |
|-------|------|------|--------|------|
