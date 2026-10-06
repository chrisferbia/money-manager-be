# Receivables by description

GET /reports/receivables?account_id=N aggregates all saved transfers for one
workspace-owned ledger account. Missing/foreign accounts return 404; crypto
accounts return 400; invalid IDs return 422. /demo/reports/receivables uses the
reserved unclaimed demo workspace and cannot read any private account.

Group by NULLIF(TRIM(description), '') with case-sensitive grouping. Each item
contains description, lent (destination), repaid (source), outstanding (difference),
and transaction_count. Sort descending by outstanding, then name. Ignore income
and expenses. Do not filter dates or paginate totals. No migration or writes.
