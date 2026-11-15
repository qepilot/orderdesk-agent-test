---
name: sql-performance-analysis
description: Procedure for diagnosing slow queries and reviewing schema migrations (indexes, execution plans, locking, safe rollout). Load it for latency regressions, slow-query reports and any pull request that touches migrations/.
---

# SQL performance analysis

Work in this order and do not skip a step because the answer seems obvious.

1. **Measure before you theorise.** `get_slow_queries` first. Name the statement, how often it runs and how long it takes.
2. **Read the plan.** `get_query_plan` for saved production plans, `explain_query` for the workshop copy.
   Warning signs: a sequential scan with many rows removed by the filter; a sort that an index could provide;
   a loop count in the thousands.
3. **Check the indexes** with `describe_schema <table>`. An index helps a query when its leading columns are the
   equality predicates and the next column is the ORDER BY column. A function around a column or a leading `%`
   in LIKE prevents index use.
4. **Find what changed.** `list_commits` for `migrations`, then read the migrations since the regression began.
   Table rebuilds drop indexes; renamed columns invalidate them.
5. **Look at the caller.** One query per row of a previous result (N+1) multiplies any slowness.
6. **Propose the smallest safe change** and how to verify it.

## Reviewing a migration

Report each of these that applies, with the line:

- `CREATE INDEX` without `CONCURRENTLY` on a large table (blocks writes).
- `ADD COLUMN ... NOT NULL` without a default; a default that rewrites the table on old engine versions.
- An `UPDATE` or `DELETE` of every row in one statement.
- A change the currently running application version cannot work with (rolling deploys run old and new together).
- Composite index column order that does not match the query (equality columns first, then the sort column).
- No down migration; unrelated changes bundled together; run planned for business hours.

## Output

State the cause as "statement X does Y because Z", give the before and after plan lines as evidence, and give the
exact DDL you recommend.
