## gRPC & Protobuf Panel

*Activation is governed by the trigger table in `context/panels/triggers.md` — that table is the single source for the file patterns and dependency signals that load this panel. Cross-service delivery concerns (queues, sagas, outbox) live in `distributed.md`; generic HTTP concerns live in `http-api.md`; this panel covers the protobuf wire contract and gRPC call semantics.*

- **Kenton Varda** — original Protocol Buffers v2 lead at Google; author of Cap'n Proto; wire-format and schema-evolution semantics
- **Eric Anderson** — gRPC-Java tech lead and long-time gRPC maintainer; deadlines, retries, and channel/streaming lifecycle

**Varda's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Field numbers are the wire contract** | The wire format is keyed on field *number*, not name. A number, once shipped, is immutable — reusing or renumbering it silently misinterprets old bytes. Reserve retired numbers with `reserved`; renaming a field is safe, renumbering is a data-corruption bug. |
| **Wire compatibility has precise rules** | Adding an optional field is safe; changing a field's type is usually not; `int32`/`int64`/`bool` are varint-compatible while `int32`/`fixed32` are not. Making a field `required` (proto2) is a one-way door — prefer optional-with-validation. |
| **Unknown fields must be preserved, not dropped** | A relay/proxy that parses and re-serializes a message must retain unknown fields, or a new field is stripped when an old intermediary forwards it — a silent data-loss path across mixed-version deployments. |

**Anderson's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Deadlines propagate or the system hangs** | Every RPC should carry a deadline, and a server making downstream calls must propagate the *remaining* budget, not start a fresh timeout. Absent deadlines, one slow dependency cascades into exhausted threads and hung callers across the whole call tree. |
| **Retries require idempotency** | gRPC's automatic retry and hedging policies re-send requests. Only idempotent methods are safe to retry; retrying a non-idempotent unary call duplicates effects. Configure retryable status codes deliberately, not blanket `UNAVAILABLE`-on-everything. |
| **Streams are long-lived resources** | Client/server/bidi streams hold connections and goroutines/threads. Missing flow control, no per-message deadline, or a client that never calls `CloseSend`/half-close leaks resources. Cancellation must propagate so a gone client frees the server side. |
| **Status codes carry contract meaning** | `INVALID_ARGUMENT` vs `FAILED_PRECONDITION` vs `ABORTED` tell the client whether to fix input, retry, or give up. Returning `INTERNAL`/`UNKNOWN` for everything destroys the client's ability to react correctly. |

*Synthesis:* Varda evaluates whether the `.proto` schema and its evolution keep the wire contract intact across versions. Anderson evaluates whether the runtime call semantics — deadlines, retries, streaming lifecycle, status codes — are safe under partial failure. A schema can be wire-compatible and still hang the fleet for want of deadline propagation; a call path can be beautifully deadline-managed atop a `.proto` that reused a field number. Both lenses matter.

---

## Review Dimensions

---

### Dimension 52: Protobuf Wire Contract & gRPC Call Semantics
*Varda, Anderson*

| Hazard | What to look for |
|--------|-----------------|
| **Reused or renumbered field** | A field number changed, or a retired number reassigned to a new field, without a `reserved` declaration — old bytes decode as the wrong field. |
| **Incompatible type change** | A field's type changed across a non-compatible boundary (`int32`→`string`, `int32`→`fixed32`, scalar→message) on a wire-visible message. |
| **New `required` field (proto2)** | Adding `required`, or tightening a field, breaking older producers/consumers — a one-way compatibility door. |
| **Unknown fields dropped on relay** | A proxy/transform that parses and re-serializes without preserving unknown fields, stripping newer fields across mixed versions. |
| **RPC without a deadline** | A unary or streaming call with no deadline/timeout, or a server that starts a fresh timeout instead of propagating the inbound remaining budget. |
| **Retry on non-idempotent method** | A retry or hedging policy applied to a method that mutates state without idempotency — duplicated effects on transient failure. |
| **Leaked stream** | A stream never half-closed/`CloseSend`, no flow control, or client cancellation not propagated to release server-side resources. |
| **Wrong status code** | `INTERNAL`/`UNKNOWN` returned for client-caused errors, or `OK` with an error payload — clients can't route on the result (overlap with HTTP/API when fronted by a gateway). |
| **Message size unbounded** | No max-message-size limit on a field or stream that can grow with user data — a memory-exhaustion vector. |
| **Enum zero-value misuse** | A meaningful value assigned to enum tag `0` instead of an `UNSPECIFIED` default, so an unset field is indistinguishable from a real value across versions. |

Anderson's design question: trace one inbound RPC to its slowest downstream dependency — is the deadline propagated end to end, and does client cancellation free every resource along the path? Varda's: for every field you have ever removed, is its number `reserved`, and can a message written by last quarter's binary still round-trip through today's?
