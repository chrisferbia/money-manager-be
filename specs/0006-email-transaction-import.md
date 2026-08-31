---
stage: draft
updated: 2026-08-31
---

# Spec: Email Transaction Import

## Overview
Automatically import eligible BCA transaction notification emails received by
the Cloudflare Email Worker into the money manager. The first supported flow is
Gmail forwarding BCA notifications to the configured Email Routing address.
Unrecognized or malformed emails are recorded for review and never create a
transaction.

## Dependencies
- 0001-account-master.md
- 0002-expense-categories.md
- 0003-transactions.md
- 0004-account-transfers.md
- 0005-balances-and-reporting.md

## Requirements
- [ ] **R1** — Extend the Email Worker handler to read and parse the raw MIME email, including multipart messages, and inspect the original message headers and body without forwarding the email.
- [ ] **R2** — Accept BCA notifications whose original `From` header identifies `bca@bca.co.id`, including messages forwarded through Gmail; reject unrelated senders from transaction processing and record them for review.
- [ ] **R3** — Parse successful BCA HTML notifications such as `Internet Transaction Journal`, extracting transaction status, transaction date, transfer direction/type, amount, beneficiary name, remarks, and reference number.
- [ ] **R4** — Convert a successful outgoing BCA transaction into an `expense` for the existing `bca` account using the `Other Expense` category. Convert a supported successful incoming BCA transaction into an `income` for the same account using the `Other Income` category.
- [ ] **R5** — Normalize BCA IDR amounts such as `IDR 30,000.00` to the integer amount `30000`, and normalize WIB transaction dates to UTC ISO8601 values before insertion.
- [ ] **R6** — Build the transaction description from the parsed beneficiary and remarks when present, while retaining the BCA reference number in the import record or description for traceability.
- [ ] **R7** — Prevent duplicate transactions by treating the email `Message-ID` as an idempotency key. Reprocessing the same email must not insert another transaction.
- [ ] **R8** — Add a D1 email-import log table containing the message ID, sender, recipient, subject, received time, status, failure/review reason, raw size, and created transaction ID. Do not persist the raw email body or unmasked account numbers.
- [ ] **R9** — Record unknown senders, unsupported notification formats, unsuccessful transaction statuses, missing required fields, missing `bca` account, and missing default categories as review/failure records without inserting a transaction. Log useful structured metadata to the Worker console as well.
- [ ] **R10** — Reuse the existing transaction validation and persistence rules where practical, and keep the HTTP transaction API behavior unchanged.

## Acceptance Criteria
<!-- Each maps to one or more Requirements (verifies: R#). -->
- [ ] **AC1** — A valid forwarded BCA `Internet Transaction Journal` email is parsed from its MIME HTML part and recognized by its original BCA sender. _(verifies: R1, R2, R3)_
- [ ] **AC2** — The provided successful outgoing sample creates exactly one `expense` transaction for account `bca`, with category `Other Expense`, amount `30000`, and UTC occurred time `2026-08-29T07:18:52Z`. _(verifies: R4, R5)_
- [ ] **AC3** — The imported transaction description contains the beneficiary `TJU SIAT LI` and the import retains the BCA reference number `00B3F2F7-FF98-4BD1-8135-05E55BC4191D`. _(verifies: R6, R8)_
- [ ] **AC4** — A supported successful incoming BCA notification creates one `income` transaction for account `bca` with category `Other Income`. _(verifies: R3, R4)_
- [ ] **AC5** — Processing the same message ID twice creates only one transaction and records/reports the second delivery as a duplicate. _(verifies: R7, R8)_
- [ ] **AC6** — An email from a non-BCA sender is not imported and is recorded as a review item. _(verifies: R2, R9)_
- [ ] **AC7** — A BCA email with an unsuccessful status, unsupported format, or missing amount/date is not imported and is recorded with a useful reason. _(verifies: R3, R9)_
- [ ] **AC8** — If the `bca` account or required default category is absent, no transaction is inserted and the import is recorded as failed. _(verifies: R4, R9)_
- [ ] **AC9** — The Email Worker does not call `forward()` or `setReject()` for successfully handled, duplicate, or review-only emails, and logs structured processing details. _(verifies: R1, R9)_
- [ ] **AC10** — Existing HTTP transaction creation, listing, update, and deletion tests continue to pass. _(verifies: R10)_

## Out of Scope
- Other banks or notification providers.
- Automatic creation of accounts or categories.
- Transfers between two money-manager accounts. BCA notifications in this first version are classified as income or expense according to their direction.
- Reading full email bodies back through the application UI or API.
- OCR or parsing transaction details from image/PDF attachments.
- Multi-currency transactions; only IDR notifications are supported.
- Reversals, refunds, chargebacks, or automatic correction of an already imported transaction.

## Edge Cases
- Gmail forwarding may add wrapper headers; the parser must prefer the original BCA message headers when available rather than trusting only the SMTP envelope sender.
- HTML whitespace, line breaks, casing, and formatting may vary around BCA labels and values.
- `Remarks` may be `-` or absent; the description must still be useful when beneficiary data exists.
- The same BCA email may be delivered more than once or retried by the email runtime.
- Amounts with an IDR decimal presentation of `.00` represent whole rupiah units for this application.
- An email with a valid message ID but an invalid payload must remain reviewable and must not be retried into duplicate transactions without an explicit future retry mechanism.

## Open Questions
- None. The first supported sample is an outgoing transfer from `bca`, mapped to `expense` and `Other Expense`.

## Verification Log
<!-- Appended by spec-verify, one row per evaluated item per round, newest last. -->
| Round | Date | Item | Result | Note |
|-------|------|------|--------|------|
