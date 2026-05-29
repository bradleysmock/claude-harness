## Observability Panel

*Active when service entry points, request handlers, background jobs, queue consumers, or any production code path that emits or should emit logs, metrics, traces, or events is in scope. Also active for files configuring observability infrastructure (`otel*.yaml`, logging configs, Prometheus rules, alertmanager configs).*

- **Charity Majors** — co-founder of Honeycomb; *Observability Engineering*; high-cardinality structured events, debugging in production
- **Cindy Sridharan** — *Distributed Systems Observability*; the three pillars and their relationships, sampling, instrumentation discipline

**Majors's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Observability is the ability to ask new questions of production** | If a novel failure requires a code change to investigate, you don't have observability — you have monitoring of known failures. Instrument the *attributes* of every operation (user ID, tenant, feature flags, version, region) so you can pivot on any of them. |
| **One wide event per unit of work** | A request, a job, a message handler emits *one* structured event with every dimension you might want to query later, not 20 separate log lines. Reconstructing what happened from log fragments is a search problem. |
| **High cardinality is the point** | The interesting questions ("did this fail for one specific user?", "is this slow only for one feature flag variant?") require high-cardinality dimensions. Metric labels can't hold them — events can. |
| **Production is the test environment** | No staging environment reproduces production traffic patterns. Observability lets you make small changes with confidence because you can see the effect immediately. |
| **Logging at debug level isn't observability** | A 10x log volume increase under load doesn't tell you anything new — it tells you the same thing 10x faster. Instrument structure, not verbosity. |

**Sridharan's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Logs, metrics, and traces serve different questions** | Metrics: aggregate trends, alertable. Traces: causal flow across services for one request. Logs: textual context within a span. They're not interchangeable. Pick the right primitive per question. |
| **Trace context must propagate or it's useless** | A trace ID generated at the edge but lost across an async boundary (queue, `setTimeout`, `to_thread`, RPC) breaks the causal chain. Every boundary needs explicit propagation. |
| **Metric cardinality is a budget** | High-cardinality labels (user ID, request ID, URL with IDs) on metrics blow up storage and query cost. Push high cardinality into traces/events; keep metrics low-cardinality. |
| **Sampling decisions are part of the design** | Trace 100% of errors. Trace 100% of slow requests. Trace a sample of healthy requests. Head sampling vs. tail sampling has different cost/visibility tradeoffs — pick one deliberately. |
| **Logs without structure don't aggregate** | `logger.info(f"User {user_id} did {action}")` is a search problem. `logger.info("user_action", user_id=user_id, action=action)` is a query. |

*Synthesis:* Majors and Sridharan agree that structured, high-cardinality data is the foundation. They differ on emphasis: Majors pushes toward wide events as the primary primitive; Sridharan keeps the three pillars distinct and emphasizes choosing the right one per question. The synthesis: emit one wide structured event per unit of work, propagate trace context across every boundary, reserve metrics for alertable low-cardinality aggregates.

---

## Review Dimensions

---

### Dimension 23: Observability & Telemetry Discipline
*Majors, Sridharan*

| Hazard | What to look for |
|--------|-----------------|
| **Unstructured log strings** | `logger.info(f"processed {n} items in {ms}ms")` — searchable but not queryable. Use structured kv: `logger.info("batch_processed", count=n, duration_ms=ms)`. |
| **Missing trace context propagation** | An async boundary (queue producer/consumer, background task, `to_thread`, fan-out gather) without explicit trace context handoff. The trace ends at the boundary; downstream work is unattributed. |
| **PII in logs or trace attributes** | Email, phone, full name, IP, request body fragments emitted to telemetry without redaction. Log destinations have their own access model — they shouldn't multiply the PII surface. |
| **High-cardinality metric labels** | Prometheus/OTEL metrics labeled with user ID, request ID, URL containing IDs, error message strings. Time-series blow up; queries get slow. |
| **Log-and-rethrow noise** | `catch` block that logs and re-raises — every layer above logs the same error. The top-level handler should log once with full context. |
| **Missing error context** | Exceptions logged without the inputs that caused them ("ValueError: invalid input" with no indication of what input). Hard to reproduce. |
| **No instrumentation at trust boundaries** | LLM calls (Dimension 15), DB queries past a threshold, external HTTP requests, queue ops — these are the places where weird things happen. They must be instrumented. |
| **Metrics without alerts; alerts without runbooks** | A dashboard nobody watches; an alert that fires without a documented response. Either delete it or wire it to a destination. |
| **Single log level for everything** | Code that logs everything at `info` (or `debug`). Levels exist to separate "what an operator wants to see by default" from "what a developer needs when investigating." |
| **Sampling without intent** | 1% sampling of all traces — including all errors, which are the ones you needed. Sample healthy traffic; keep errors / slow requests at 100%. |
| **Logging credentials or tokens** | Authorization headers, API keys, session tokens appearing in any log destination. Often via wholesale `logger.info(request_dict)`. |
| **No deploy/version dimension** | Telemetry events without the deployed version or commit SHA. Can't distinguish "broken since deploy" from "always broken." |
| **Alerting on symptoms, not user impact** | Alerts on CPU > 80% or queue depth > 1000 — these are conditions, not user impact. Alert on user-facing SLO violations (latency, error rate); investigate conditions. |
| **Print/console.log in production paths** | `print(...)` / `console.log(...)` in non-test code. Goes to stdout with no structure, level, or destination control. Use the project logger. |
| **Unnamed spans** | Trace spans with auto-generated or generic names (`"task"`, `"handler"`) — useless in a trace UI. Name spans for the operation. |

Majors's design question: when a customer reports "it was slow for me at 3pm," can you isolate exactly which of their requests, which dependencies were involved, and what was different about them — without shipping a code change?
