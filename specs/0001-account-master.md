---
stage: tested
updated: 2026-08-10
---

# Spec: Account Master

## Overview
Lets the user define and manage the accounts they track money in (e.g. cash, debit card). This is foundational reference data that transactions and transfers will attach to in later specs. Introduces the FastAPI + Pydantic setup that all subsequent specs build on: `entry.py` becomes a thin ASGI bridge (`asgi.fetch(app, request, self.env)`), route handlers reach the D1 binding via `request.scope["env"]`, and request/response bodies are validated with Pydantic models.

## Requirements
- [ ] **R1** — Add an `accounts` table to the D1 schema: `id` (integer, autoincrement primary key), `name` (text, required, unique), `type` (text, required, free-form e.g. "cash"/"debit_card"), `created_at` (text, default current timestamp).
- [ ] **R2** — `entry.py` is rewritten as a FastAPI app served via `asgi.fetch`, replacing the current manual `qtable` query; the `qtable` table/query is removed from `db_init.sql` and the code.
- [ ] **R3** — `POST /accounts` creates an account given `name` and `type`; rejects blank `name`/`type` and duplicate `name`.
- [ ] **R4** — `GET /accounts` lists all accounts.
- [ ] **R5** — `GET /accounts/{id}` returns a single account or 404 if not found.
- [ ] **R6** — `PATCH /accounts/{id}` updates `name` and/or `type`; same validation as create.
- [ ] **R7** — `DELETE /accounts/{id}` removes an account; returns 404 if not found. (Deletion is blocked once transactions exist, per **0003-transactions.md** — tracked there since the `transactions` table doesn't exist yet.)

## Acceptance Criteria
<!-- Each maps to one or more Requirements (verifies: R#). -->
- [ ] **AC1** — Creating an account with a valid name/type returns 201 and the created account with an `id`. _(verifies: R1, R3)_
- [ ] **AC2** — Creating an account with a blank name, blank type, or a name that already exists returns a 4xx error and no row is inserted. _(verifies: R3)_
- [ ] **AC3** — `GET /accounts` returns all created accounts. _(verifies: R4)_
- [ ] **AC4** — `GET /accounts/{id}` returns the matching account, or 404 for an unknown id. _(verifies: R5)_
- [ ] **AC5** — `PATCH /accounts/{id}` persists the updated fields; invalid updates (blank name/type, duplicate name) are rejected. _(verifies: R6)_
- [ ] **AC6** — `DELETE /accounts/{id}` removes the account, and a subsequent `GET /accounts/{id}` returns 404. _(verifies: R7)_
- [ ] **AC7** — The old `/` quote endpoint and `qtable` are gone; hitting the Worker's root now reaches the FastAPI app. _(verifies: R2)_

## Out of Scope
- Account balances (needs the transaction ledger — see **0005-balances-and-reporting.md**).
- Blocking deletion of accounts with existing transactions (needs the `transactions` table — see **0003-transactions.md**).
- Multi-user/auth, multi-currency.

## Edge Cases
- Duplicate account name (case-sensitive exact match) is rejected.
- Updating an account to a name that collides with a *different* existing account is rejected; renaming to its own current name is allowed.

## Open Questions
- Should `type` be constrained to a fixed enum (cash/debit_card/credit_card/e_wallet/savings/other) or stay free text? Currently spec'd as free text validated non-empty — revisit if the frontend needs a fixed picker list.

## Verification Log
<!-- Appended by spec-verify, one row per evaluated item per round, newest last. -->
| Round | Date | Item | Result | Note |
|-------|------|------|--------|------|
