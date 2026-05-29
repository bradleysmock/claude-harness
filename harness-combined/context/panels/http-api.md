## HTTP & API Design Panel

*Active when files whose path contains `route`, `handler`, `controller`, `endpoint`, `view`, `api`, or `resources` are in scope; OpenAPI / AsyncAPI / JSON Schema specs (`openapi.{yaml,json}`, `swagger.{yaml,json}`); files registering HTTP routes; or `**/*.go` with HTTP patterns. For HTMX-specific hypermedia concerns see `hypermedia.md`; for GraphQL/gRPC-specific concerns this panel covers the cross-cutting issues but defers deep idiom questions to those communities.*

- **Roy Fielding** — author of the REST dissertation; HTTP/1.1 spec editor; the architectural constraints that make HTTP work
- **Mark Nottingham** — IETF HTTPbis working group chair; HTTP semantics, caching, problem+json (RFC 7807), structured headers, conditional requests
- **Phil Sturgeon** — *Build APIs You Won't Hate*; OpenAPI discipline, API evolution, pragmatic REST, the contract-first vs code-first tradeoff

**Fielding's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **The uniform interface is the constraint that pays the bills** | REST's value comes from honoring the four sub-constraints: identification of resources, manipulation through representations, self-descriptive messages, hypermedia as the engine of state. APIs that bypass the uniform interface (operations encoded in URL paths like `/api/getUserById`, custom verbs in POST bodies) forfeit the cacheability, intermediary, and evolvability benefits — and then complain that "REST doesn't scale." |
| **Statelessness is a per-message property** | Each request must carry the context needed to process it. Server-side session state pinned to a specific server breaks load balancing and recovery. Bearer tokens are stateless; sticky-cookie sessions are not. |
| **HATEOAS is a design choice with a cost** | Hypermedia controls (links, forms) in responses let clients discover transitions without out-of-band documentation. Worth it for public APIs with long-lived heterogeneous clients; often overkill for internal APIs with generated clients. The mistake is doing it halfway — partial HATEOAS is worse than none. |
| **Method semantics are infrastructure contracts** | GET is safe and idempotent — caches, prefetchers, and crawlers depend on this. PUT and DELETE are idempotent — retry logic depends on this. POST is neither. Violations (GET that mutates, POST for retrieval, non-idempotent PUT) break every cache, proxy, and retry mechanism on the path. |
| **Cool URIs don't change** | A URI is a public identifier. Renaming it breaks every bookmark, link, log line, and cached representation. Plan URI structure as if it's forever; reserve `/v1/` for the cases where you genuinely cannot evolve in place. |

**Nottingham's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Status codes are a contract, not decoration** | 2xx success, 3xx redirect, 4xx client fault, 5xx server fault. `200 OK` with `{"error": "..."}` body is widespread but breaks intermediaries, observability, and client SDK error handling. `422 Unprocessable Entity` for semantic validation, `409 Conflict` for state conflicts, `429 Too Many Requests` with `Retry-After`, `503 Service Unavailable` for overload. |
| **Caching is HTTP's free lunch** | `Cache-Control`, `ETag`, `Last-Modified`, `Vary` are the difference between "fast at scale" and "every request hits origin." A response without explicit cache directives lets intermediaries cache (or refuse to cache) on heuristics — surprising in both directions. |
| **Content negotiation lets one URL serve many representations** | `Accept: application/json` vs. `application/vnd.api+json` vs. `text/csv` against the same URL. Versioning via Accept (`application/vnd.acme.v2+json`) keeps URLs stable; URL versioning is also valid but pick one and document the choice. |
| **Problem Details (RFC 7807)** | Error responses with `application/problem+json` carry `type`, `title`, `status`, `detail`, `instance`. Bespoke error shapes per endpoint are debt; problem+json is the standard and tooling assumes it. |
| **Conditional requests** | `If-Match` / `If-None-Match` with ETags enables safe concurrent edits (precondition failed → 412) and bandwidth-efficient revalidation. Skipping them invites lost updates and wasted bandwidth. |
| **Structured Headers (RFC 8941)** | New headers should use the structured-headers grammar. Old headers with custom parsing (semicolons, commas, key=value mixes) are an interop trap; if you must invent one, use the standard form. |

**Sturgeon's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **OpenAPI is the contract; make it authoritative** | Hand-written endpoints with hand-edited docs drift. Either generate the spec from code under CI enforcement, or generate code and types from the spec — but one source of truth, validated against the running service in tests. |
| **Versioning is forever** | Once a client depends on `/v1/foo`, you support it until the last client is dead. Plan deprecation timelines from day one. Prefer additive evolution (new optional fields, new endpoints) over breaking changes; reserve version bumps for changes additive evolution can't express. |
| **Idempotency keys at the mutating boundary** | Every POST that creates and every PATCH that mutates accepts an `Idempotency-Key` header. Retries hit the same key and get the same response — the only safe way clients implement at-least-once over an unreliable network. Without this, every network blip risks duplicate charges, duplicate emails, duplicate records. |
| **Pagination consistently, with `Link` headers** | RFC 5988 `Link` headers for `next`/`prev`/`first`/`last`. Cursor pagination scales; offset pagination doesn't past the first few pages (Dimension 19 overlap). Pick a scheme per collection, document it, and don't mix. |
| **Rate limits are part of the contract** | `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset` (IETF draft). `429` with `Retry-After`. Silent throttling, degraded-but-200 responses, and per-endpoint limits without documentation are all client-hostile. |
| **Document the failure modes** | Happy-path docs are easy. Real APIs are judged on how they document timeouts, partial failures, retry semantics, idempotency boundaries, rate limits, deprecation paths — the things consumers actually trip over. |

*Synthesis:* Fielding evaluates whether the API respects the architectural constraints that make HTTP scale — uniform interface, statelessness, cacheability, layered system. Nottingham evaluates whether the HTTP-level semantics are correct — status codes, caching, conditional requests, headers. Sturgeon evaluates whether the API is a contract a downstream consumer can build against without consulting source. An endpoint can be REST-pure and undocumented, beautifully specified and using wrong methods, or perfectly behaved on HTTP but unsafe to retry. All three lenses matter.

---

## Review Dimensions

---

### Dimension 31: HTTP/API Design & Contract
*Fielding, Nottingham, Sturgeon*

| Hazard | What to look for |
|--------|-----------------|
| **Wrong status code** | `200` for failures with error in body; `500` for client-caused validation errors; `404` for authorization failures (leaks existence of the resource); `500` where `503` would correctly tell load balancers to back off. |
| **Method abuse** | `GET` that mutates state — breaks caches, prefetchers, browser history. `POST` for retrieval — uncacheable. `PUT` or `DELETE` that is not idempotent — retries cause duplicate effects. |
| **Bespoke error shape per endpoint** | Each endpoint returns a different error JSON. Use `application/problem+json` (RFC 7807) consistently across the API. |
| **No idempotency key on mutating endpoints** | `POST /charges`, `POST /orders`, `PATCH /users/:id` without `Idempotency-Key` support. Network retry creates duplicate charges, duplicate orders, or undoes intermediate state. |
| **Versioning strategy chosen by accident** | URL versioning (`/v1/`) and Accept-header versioning are both defensible; mixing them across the same API, or shipping `/v1/` without a documented sunset policy, is the smell. |
| **Breaking change without deprecation** | Removing a field, tightening validation, changing default values, narrowing accepted types — without a deprecation window, `Sunset` header (RFC 8594), or version bump. |
| **Missing pagination** | `GET /things` that returns all rows. Or paginated only by `?page=N&size=M` with no documented maximum size. Endpoint becomes a DoS vector and a latency disaster as data grows. |
| **`OFFSET` pagination on a growing collection** | Past the first few pages, `OFFSET N` reads and discards N rows (Dimension 19 overlap). Use keyset/cursor pagination for any collection that grows. |
| **Pagination without `Link` headers** | Pagination state encoded only in the body. Clients invent their own conventions for parsing it; intermediaries can't follow the chain. Use RFC 5988 `Link` headers (`rel="next"`, `rel="prev"`). |
| **OpenAPI absent, hand-edited, or unverified** | No spec; or a spec hand-written and stale; or a spec generated but never validated against the running service in CI. The contract that isn't tested is fiction. |
| **No request validation at the boundary** | Endpoint accepts JSON bodies without schema validation — bad input flows into business logic and produces 500s far from cause. Validate against the OpenAPI/JSON Schema at the edge. |
| **No response validation in tests** | Tests assert on happy-path response shape but never validate the response *against the published schema*. Schema and implementation drift; consumers break. |
| **Permissive CORS on authenticated endpoints** | `Access-Control-Allow-Origin: *` paired with cookies or `Allow-Credentials: true` — the latter is rejected by browsers with wildcard origin but the intent is wrong; explicit allowlist required. Pre-flight handling missing or wrong. |
| **No rate limit / no `Retry-After`** | Endpoint with no rate-limiting that can be hammered. Or rate-limited but returns `429` without `Retry-After` — clients re-hammer immediately. |
| **Authentication via query string** | API key or token in URL — logged by every proxy, server log, and CDN; leaks via `Referer`. Use `Authorization` header. |
| **Authorization at the wrong layer** | Permission check in the controller but not in the service or repository — bypassable via internal callers, background jobs, or admin endpoints (overlap with Core security). Defense in depth: enforce at every layer that can be entered. |
| **No conditional request support** | Resources mutated frequently with no `ETag` / `Last-Modified` — every client polls full payloads. No `If-Match` support — concurrent edits silently overwrite each other. |
| **No content negotiation, hardcoded to JSON** | Endpoint serves only `application/json` when consumers want CSV exports, Protobuf, or `application/vnd.api+json`. Multiple endpoints per format multiply surface area. Negotiate via `Accept`. |
| **Self-descriptive failure missing** | Validation failure responses that say "invalid request" but not *which* field, *why*, or *how to fix*. Use `application/problem+json` with `errors[]` containing field-level detail. |
| **Sensitive data in URLs** | User IDs, tokens, emails, account numbers in URL paths/queries — logged everywhere, leaked in `Referer`, cached by intermediaries. Use opaque IDs in URLs; put sensitive material in body or headers. |
| **HATEOAS done halfway** | Some responses include hypermedia links; others don't. Some links are absolute, others relative. Some use `Link` headers, others embed `_links`. Pick one form and apply it everywhere — partial HATEOAS is worse than declining it. |
| **GraphQL without depth/complexity limits** | If using GraphQL: no max query depth, no complexity budget, resolvers issuing per-edge queries. Single malicious query can DoS the database (overlap with Dimension 19). |
| **gRPC status not mapped to HTTP** | gRPC service exposed via HTTP gateway returning raw gRPC status codes (`13 INTERNAL`) instead of mapped HTTP codes. Clients downstream can't route on response. |
| **Cool URIs that aren't** | URLs that include the implementation framework (`/api.php`), the storage tech (`/mongo/`), the team name (`/billing-team/`), or auto-generated IDs that change on redeploy. These are renames waiting to happen. |
| **Webhooks without signature verification** | Inbound `/webhooks/...` endpoints accepting POSTs without HMAC or asymmetric signature verification (overlap with Distributed panel). |
| **No `Sunset` header on deprecated endpoints** | Endpoint marked deprecated in docs but the wire response carries no `Sunset` or `Deprecation` header. Programmatic consumers have no signal. |

Fielding's design question: if a new client is written from your OpenAPI spec alone — no source access, no maintainer Slack — can they integrate? If not, what's missing from the spec, and is the gap a documentation problem or a design problem?

Sturgeon's: for every breaking change you've ever shipped, can you point to the deprecation window, the `Sunset` header dates, and the consumer-impact analysis that preceded it? If "breaking change" is a phrase that doesn't enter your team's vocabulary until release day, the API is not yet a contract.
