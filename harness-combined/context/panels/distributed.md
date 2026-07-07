## Distributed Systems Panel

*Activation is governed by the trigger table in `skills/critique/SKILL.md` — that table is the single source for the file patterns and dependency signals that load this panel.*

- **Sam Newman** — *Building Microservices*, *Monolith to Microservices*; service boundaries, decomposition, the cost of distribution
- **Chris Richardson** — *Microservices Patterns*; saga pattern, outbox, transactional messaging, idempotency

**Newman's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Distribution has a cost; pay it deliberately** | Every network call adds failure modes, latency, and a serialization boundary. "Microservices" as a default architecture imposes this cost on every interaction — fine if the boundary is real, expensive if it's invented. |
| **Service boundaries follow domain boundaries** | A good service boundary is a bounded context (Evans, Core panel). Splitting along technical lines ("the database service," "the auth service") instead of domain lines produces tightly coupled distribution. |
| **No shared database between services** | If two services read/write the same table, they aren't two services — they're one service with a network in the middle. The database is an internal implementation detail of *one* service. |
| **Synchronous calls couple availability** | Service A calling Service B synchronously means A's uptime is bounded by B's. Each hop multiplies failure probability. Prefer async messaging where the domain allows. |
| **Consumer-driven contracts** | The consumer specifies what shape it needs; the provider verifies. Schema changes that break the consumer fail the provider's CI, not the consumer's runtime. |

**Richardson's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **At-least-once delivery + idempotent consumers** | Distributed messaging guarantees at-least-once delivery (or you build at-most-once with data loss). The consumer must be idempotent — handle the same message twice with the same outcome. |
| **The dual-write problem** | "Write to DB then publish to queue" is two operations that can partially fail. Solution: the outbox pattern — write the event to an outbox table in the same transaction, then a separate process publishes from the outbox. |
| **Sagas, not distributed transactions** | Two-phase commit across services doesn't scale and doesn't compose. Use a saga: a sequence of local transactions, each with a compensating action if a later step fails. The saga's correctness is the application's responsibility. |
| **Idempotency keys at the API boundary** | Every state-mutating API takes an idempotency key. Retries (network failures, client retries) hit the same key and get the same response. |
| **Event-carried state transfer over query-on-demand** | If service B needs data owned by A, having B query A on every operation creates synchronous coupling. Instead, A publishes events; B maintains a local read model. Tradeoff: eventual consistency. |

*Synthesis:* Newman evaluates whether the system *should* be distributed at this boundary — is there a real domain seam, or did we invent one. Richardson evaluates whether the distributed mechanism is *correct* — that retries don't double-bill, that crashes don't lose events, that compensations actually compensate.

---

## Review Dimensions

---

### Dimension 26: Distributed Systems & Messaging Correctness
*Newman, Richardson*

| Hazard | What to look for |
|--------|-----------------|
| **Dual write without outbox** | A handler that writes to the database and then publishes to a queue / calls another service. Crash between the two leaves an inconsistency invisible to both sides. Use an outbox table or transactional messaging. |
| **Non-idempotent message consumer** | A consumer that creates a record without checking for prior processing — duplicate delivery creates duplicates. Use message ID or business key for dedup. |
| **No idempotency key on mutating API** | A POST endpoint that creates a charge, sends an email, or transfers state, with no `Idempotency-Key` header support. A retry under flaky network double-acts. |
| **Synchronous chain across services** | A request handler that calls service B which calls C which calls D, all synchronously. Failure probability multiplies; latency adds. Reconsider whether async or co-location is right. |
| **Shared database table across services** | Two services reading or writing the same table. They are not independent services; schema changes coordinate across teams. Either merge or expose via API. |
| **Retry without backoff / jitter** | Tight retry loop on failure → retry storm during partial outage → worsens the outage. Exponential backoff with jitter; honor `Retry-After` headers. |
| **Retry on non-retriable errors** | Retrying on 400, 401, 403, 404, validation failures — the retry will never succeed. Distinguish transient (5xx, network, timeout) from terminal. |
| **Missing circuit breaker on external call** | An external call with no failure threshold / open-circuit behavior. When the downstream is dead, every request blocks waiting for timeout. |
| **No timeout on RPC / HTTP call** | Default timeout is "infinity" for many clients. One slow downstream → request handlers stack up → server runs out of connections. |
| **At-most-once where at-least-once is needed** | "Fire and forget" event publishing where the receiver's processing matters. Lost events are silent data loss. |
| **Distributed transaction across services** | Code attempting two-phase commit, distributed locks for invariants spanning services, or `BEGIN/COMMIT` across multiple databases. Use a saga with compensations. |
| **Saga without compensation** | A multi-step process where intermediate failure leaves later steps un-rolled-back. Charge the card, then fail to ship — no refund step. |
| **Webhook handler without signature verification** | A `/webhooks/...` endpoint accepting POSTs without HMAC verification of the sender. Any caller can inject events. |
| **Ordering assumed across partitions** | Code that assumes messages arrive in send-order when the queue/log partitions on a key that doesn't match the order requirement (or doesn't partition at all). |
| **Schema change without versioning** | A producer changing the event schema with no version field, no backward compatibility, no consumer-driven contract test. |
| **Snapshotting via "query and store"** | Service B periodically queries Service A to keep a local cache. Race-prone, latent, and creates dependency reversal. Use event publication. |
| **No dead-letter queue** | A consumer that retries forever on a poison message, blocking the queue. Bounded retries → DLQ → alert. |
| **Cross-service auth via implicit trust** | Service B trusts requests because they came from the internal network. No mTLS, no token validation. Lateral movement is unconstrained. |

Newman's design question: for each service-to-service call in this code, what happens to the user if the called service is down for 5 minutes? If the answer is "the request hangs and times out," the call is in the wrong place.
