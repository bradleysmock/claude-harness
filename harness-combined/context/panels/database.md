## Database & Data Layer Panel

*Active when `**/migrations/**`, `**/*.sql`, `**/schema.{rb,prisma,sql}`, ORM model files (Django models, SQLAlchemy declarative classes, Prisma schema, ActiveRecord models, Ent schemas, GORM structs), or files constructing raw queries are in scope.*

- **Martin Kleppmann** — *Designing Data-Intensive Applications*; storage engines, consistency models, transactions, replication
- **Markus Winand** — *SQL Performance Explained*, use-the-index-luke.com; indexing strategy, query plans, predicate selectivity

**Kleppmann's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Transactions are an invariant boundary** | If two writes must succeed or fail together to preserve an invariant, they belong in one transaction. Application-level "transactions" composed of separate DB calls are not atomic — a crash between them leaves invalid state. |
| **Isolation levels matter** | Read Committed (Postgres default) does not prevent lost updates, write skew, or phantom reads. Code that reads a row, computes a value, and writes it back without `SELECT ... FOR UPDATE` or higher isolation is racing other writers. |
| **Schema is a contract** | Adding a column is cheap. Adding NOT NULL to an existing column on a large table without a default takes a long lock. Renaming a column breaks every reader. Online migration strategies (expand-contract, dual-write) exist for a reason. |
| **Reads aren't free** | Read replicas drift. A write-then-immediate-read pattern that hits a replica returns stale data. "Read your writes" needs primary routing or session affinity, not a hope. |
| **Eventual consistency is a UX problem first** | If the system is eventually consistent, the UI must reflect that — optimistic updates, explicit "syncing" states. Surfacing stale data as fresh is a bug, not a tradeoff. |
| **Backups you haven't restored are wishes** | A backup process that has never been exercised end-to-end against a real recovery scenario is not a backup. |

**Winand's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **The leftmost index column rule** | A B-tree index on `(a, b, c)` serves `WHERE a = ?`, `WHERE a = ? AND b = ?`, and `WHERE a = ? AND b = ? AND c = ?`. It does not serve `WHERE b = ?`. Index column order is not arbitrary. |
| **Functions on indexed columns break the index** | `WHERE lower(email) = ?` does not use an index on `email` — needs a functional index on `lower(email)` or stored normalized data. Same for `WHERE date(created_at) = ?`, `WHERE substr(...) = ?`. |
| **`SELECT *` is a maintenance trap** | Column added → query suddenly returns more data → app code expects a fixed shape → bug. List columns explicitly. |
| **The N+1 query** | Iterating over a parent collection and querying children one-by-one. Use joins, batch loaders, or ORM eager-loading (`.select_related`, `.prefetch_related`, `include`). |
| **Pagination via OFFSET is O(N)** | `OFFSET 100000 LIMIT 20` reads and discards 100,000 rows. Use keyset pagination (`WHERE id > last_seen_id ORDER BY id LIMIT 20`) for stable performance. |
| **Foreign keys without indexes** | Most databases do not auto-index FK columns. Deletes on the parent then take a full scan of the child table. Index every FK column. |

*Synthesis:* Kleppmann evaluates whether the data layer preserves the invariants the application assumes. Winand evaluates whether the queries the application makes are sustainable as data grows. A schema can be correct but unindexed; a query can be fast at 1K rows and unusable at 1M.

---

## Review Dimensions

---

### Dimension 18: Schema, Migrations & Transactional Integrity
*Kleppmann*

| Hazard | What to look for |
|--------|-----------------|
| **Multi-statement writes without a transaction** | Two or more INSERT/UPDATE/DELETE that must succeed together, executed as separate statements without `BEGIN`/`COMMIT` or an ORM transaction wrapper. |
| **Read-modify-write races** | Code that `SELECT`s a value, computes a new one in application code, and `UPDATE`s — without `SELECT ... FOR UPDATE`, optimistic locking (`version` column), or an atomic SQL expression (`UPDATE x SET n = n + 1`). |
| **Unsafe online migration** | Adding `NOT NULL` to a populated column without a default and without a backfill step; renaming a column readers still reference; dropping a column writers still write; adding an index on a large table without `CONCURRENTLY` (Postgres). |
| **Cascade surprise** | `ON DELETE CASCADE` on a relationship the application doesn't expect to cascade — a parent delete silently removes years of child rows. Conversely, missing `ON DELETE` clause leaving the relationship enforced only at the app layer. |
| **Nullable when it shouldn't be** | A column the application treats as required, modeled as nullable in the schema. Or the opposite — `NOT NULL DEFAULT ''` masking the difference between "no value" and "empty value". |
| **Stale read after write** | Code that writes to the primary then immediately reads from a replica without primary-pinning. |
| **Implicit type coercion across columns** | Joining `INT` to `BIGINT`, `VARCHAR` to `TEXT`, `TIMESTAMP` to `TIMESTAMPTZ` — works but defeats indexes and changes semantics (timezone, truncation). |
| **No irreversibility marker on destructive migrations** | A migration dropping a column or table without explicit confirmation in code, no documented rollback. |
| **Money/time as float** | `FLOAT`/`REAL` for currency or precise time. Use `DECIMAL` for money and timezone-aware `TIMESTAMPTZ` for time. |
| **Soft delete without scope discipline** | `deleted_at` column added but only some queries filter it. Half the code sees deleted rows; the other half doesn't. |

---

### Dimension 19: Query Shape & Index Strategy
*Winand*

| Hazard | What to look for |
|--------|-----------------|
| **N+1 query pattern** | `for parent in parents: parent.children` or equivalent — one query per parent. Use eager loading or a single join. |
| **Function on an indexed predicate** | `WHERE lower(email) = ?` against an index on `email`. Needs a functional index or store the normalized form. |
| **`SELECT *` in production code** | Returns more data as columns are added; couples application to schema shape. List columns. |
| **`OFFSET` pagination on large tables** | `LIMIT/OFFSET` past the first few pages — O(N) cost. Use keyset pagination. |
| **Unindexed foreign keys** | FK columns without an index — deletes on the parent require a full scan of the child. |
| **Missing composite index** | Query filters on `(a, b)` repeatedly but only single-column indexes on `a` and `b` exist. |
| **Wrong column order in composite index** | Index on `(low_cardinality, high_cardinality)` queried by `WHERE high_cardinality = ?` alone — index unused. |
| **Implicit full-table scan** | `WHERE NOT IN (...)`, `WHERE col LIKE '%suffix'`, `OR` across unindexed columns. |
| **Missing query timeout** | A long-running analytical query against an OLTP database with no `statement_timeout` or equivalent — can block writers indefinitely. |
| **ORM serializing the world** | `Model.objects.all()` returning every row into application memory, then filtered in Python. Filter in the database. |
| **`COUNT(*)` on large tables for pagination UI** | Computing exact total count on every paginated request — full scan. Use approximate counts or omit the total. |
| **Index added without considering write cost** | New index on a high-write table; every INSERT/UPDATE now maintains an additional structure. Measure write throughput impact. |

Winand's design question: for every query that runs at production scale, can you point to the index that serves it and explain why that index is chosen over alternatives?
