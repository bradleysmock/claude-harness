## GraphQL Panel

*Activation is governed by the trigger table in `skills/critique/SKILL.md` — that table is the single source for the file patterns and dependency signals that load this panel. Generic HTTP correctness (status codes, caching, versioning) lives in `http-api.md`; this panel covers the GraphQL-specific layer on top.*

- **Lee Byron** — co-creator of GraphQL; author of DataLoader; schema design and the execution model
- **Marc-André Giroux** — *Production Ready GraphQL*; schema evolution, per-field authorization, and query-cost defense at scale

**Byron's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **The schema is the contract** | The type system is the API's public surface. Nullability, field naming, and deprecation are forever the moment a client depends on them. Prefer additive evolution and `@deprecated` over breaking a field; a non-null field can never later become nullable without breaking clients. |
| **Resolvers run per field, so N+1 is the default** | A naïve resolver that queries per parent produces one query per edge. Batch with DataLoader (per-request, not per-process — a shared loader leaks data across users) so a list-of-N never fans out to N round-trips. |
| **A field is not free** | Every field has a resolver and a cost. "Just expose it" grows the blast radius of every query. Model the graph around client use cases, not around the database schema. |

**Giroux's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Authorization is per field, not per endpoint** | There is one endpoint; the graph is the boundary. A single object may be reachable through many paths, so authz must be enforced in the resolver (or the business layer it calls), never assumed from the entry query. Field-level checks that live only in the top-level query are bypassable through a sibling edge. |
| **Unbounded queries are a DoS primitive** | Without a depth limit, a complexity/cost budget, or pagination, one deeply-nested or wide query can exhaust the database. Enforce max depth, assign field costs, and reject over-budget queries before execution. |
| **Public queries should be persisted (allow-listed)** | Arbitrary query strings from untrusted clients are an open attack surface. Persisted/allow-listed operations turn the API into a known, cacheable, cost-bounded set. |

*Synthesis:* Byron evaluates whether the schema and execution model are sound — nullability, evolution, and batched resolution. Giroux evaluates whether the graph is safe to expose — per-field authz, query-cost bounds, and persisted operations. A schema can be beautifully typed and still be a DoS vector; it can be cost-bounded and still leak data through an unguarded edge. Both lenses matter.

---

## Review Dimensions

---

### Dimension 51: GraphQL Schema, Resolution & Exposure
*Byron, Giroux*

| Hazard | What to look for |
|--------|-----------------|
| **N+1 resolvers** | A field resolver issuing a query per parent object with no DataLoader batching. A list field that fans out to one round-trip per element. |
| **DataLoader shared across requests** | A loader instantiated at module/process scope rather than per-request — caches and batches leak data across users. |
| **Missing per-field authorization** | Authz checked only at the top-level query/mutation, not in the resolver of a sensitive field reachable through a sibling edge. |
| **No query depth or complexity limit** | No max-depth guard and no per-field cost budget — a nested or wide query can exhaust the database. |
| **Arbitrary queries on a public endpoint** | Untrusted clients send free-form query strings with no persisted-query / allow-list — unbounded, uncacheable attack surface. |
| **Breaking schema change** | A field made non-nullable → nullable, renamed, removed, or an enum value dropped without `@deprecated` and a migration window. |
| **Errors leak internals** | Resolver exceptions surfaced to clients with stack traces, SQL, or internal paths instead of typed, sanitized GraphQL errors. |
| **Mutations that aren't idempotent-safe** | Retryable mutations with no idempotency key or client-mutation-id — network retries duplicate effects. |
| **Introspection enabled in production** | Full schema introspection exposed to untrusted clients, handing attackers the complete attack map. |
| **Pagination missing or offset-based** | List fields returning everything, or `offset`-paginated on growing collections; use cursor/connection pagination (overlap with HTTP/API Dimension 31). |

Giroux's design question: for every field that returns sensitive data, can you name the authorization check that runs in *its* resolver — not the one you assume ran at the query root? And for the worst-case query a client can send, what is its cost, and what rejects it before execution?
