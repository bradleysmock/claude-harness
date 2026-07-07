## Performance Panel

*Activation is governed by the trigger table in `skills/critique/SKILL.md` — that table is the single source for the file patterns and dependency signals that load this panel.*

- **Brendan Gregg** — *Systems Performance*; methodology, USE/RED, profiling, "know the cost of every operation"
- **Martin Thompson** — Aeron / Disruptor author; mechanical sympathy, cache behavior, lock-free design, "measure, don't guess"

**Gregg's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Measure before optimizing** | "Slow" is a hypothesis until profiled. Code reviewers who suggest performance changes without a profile are guessing. Cite the profiler output or the benchmark. |
| **The USE method (Utilization, Saturation, Errors)** | For every resource (CPU, memory, disk, network), check all three. CPU at 100% with low saturation is healthy throughput; CPU at 60% with high saturation is contention. |
| **Algorithmic before micro-optimization** | A quadratic loop will dominate any constant-factor optimization. Look for O(n²) before looking for branch misprediction. |
| **Amortize allocation in hot paths** | Allocation has a constant cost that adds up. Reuse buffers, preallocate slice capacity (`make([]T, 0, n)`), pool large objects. But only in hot paths — premature pooling is its own problem. |
| **Know the cost of every operation** | Cache hit: ~1ns. Mutex uncontended: ~25ns. RTT to local DC: ~500µs. Disk: ~10ms. Cross-region: ~100ms. Reasoning about performance requires these in your head. |

**Thompson's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Mechanical sympathy** | Write code that aligns with how hardware actually works. Sequential memory access beats random by orders of magnitude. False sharing (two threads writing adjacent cache lines) tanks throughput silently. |
| **The Disruptor pattern: pre-allocate, single writer** | Throughput-bound systems use ring buffers, not queues. Single-writer principle: one goroutine/thread owns each piece of state, eliminating contention. |
| **Lock-free is not free** | Atomics and lock-free structures aren't a magic speedup — they trade lock contention for cache contention. Use only with measurement. |
| **Tail latency, not average** | p50 latency hides everything. p99 and p99.9 are where the user experience lives. A change that improves average and worsens tail is a regression. |
| **Backpressure or collapse** | An unbounded queue is a memory leak with extra steps. Every producer/consumer relationship needs explicit backpressure — bounded buffers, rate limits, load shedding. |

*Synthesis:* Gregg and Thompson agree on the foundation: measure first, optimize second. They differ in level — Gregg is system-wide, methodology-first; Thompson is per-component, hardware-first. The synthesis: profile to find the hot spot, apply mechanical sympathy to the hot spot, measure that the change moved the metric.

---

## Review Dimensions

---

### Dimension 25: Performance Hazards
*Gregg, Thompson*

| Hazard | What to look for |
|--------|-----------------|
| **Quadratic loop on user-scaled data** | Nested iteration where the outer loop is a collection that grows with users/tenants/messages. `for x in xs: for y in xs: ...` over a 10k collection is 100M operations. |
| **Per-iteration allocation in hot path** | New slice/list/dict allocated per loop iteration when one outside the loop would do. In tight loops, allocation dominates. |
| **Unbounded queue / channel / collection** | `make(chan T)` with no explicit bound where the producer can outpace the consumer. Memory grows until OOM. |
| **No backpressure across async boundary** | Fan-out that produces work faster than consumers can drain it. Eventually consumers are overwhelmed; symptoms appear far from cause. |
| **Sync I/O on the event loop / hot path** | Blocking disk read in a Node request handler, sync DB call in an async coroutine, network call inside a render loop. |
| **Pagination missing or via OFFSET** | API endpoint or DB query that returns all results, or paginates by `OFFSET` (Dimension 19 overlap — flag at the call site here, at the query site there). |
| **Optimization without a baseline** | A change adding caches, pools, or "fast paths" with no benchmark showing the prior state was a problem. Premature, and now load-bearing complexity. |
| **Locks held across I/O** | Mutex acquired, then a network or disk call, then released. Lock duration is now I/O duration — everyone waits. |
| **False sharing / cache line contention** | Two threads/goroutines writing to fields adjacent in memory. Each write invalidates the other's cache line. Pad or separate. |
| **String concatenation in a loop** | `s = s + x` in a loop where each iteration reallocates. Use a builder (`strings.Builder`, `[]string` + `join`, `io.StringIO`). |
| **Repeated work that could be memoized** | The same expensive computation invoked multiple times per request with the same inputs. Memoize within request scope. |
| **Reading more than needed** | `SELECT *` then accessing one field; loading a full file when reading the first 1KB suffices; deserializing a full JSON blob to read one key. |
| **Worst-case tail ignored** | Code path with rare but unbounded cost (regex with catastrophic backtracking, recursive function with no depth limit, retry loop without max). |
| **Caching without invalidation strategy** | A cache added with no documented invalidation: TTL, write-through, event-driven. Stale data wins eventually. |
| **Single hot key** | Sharding/partitioning scheme where one key (a default tenant, a popular user) gets most of the traffic. The shard becomes the bottleneck. |
| **Optimization measured on cold cache** | Benchmark numbers that only hold on the first run before caches warm. Production cadence is warm. |

Gregg's design question: for the change in this diff, do you have a baseline number for the operation it affects? If not, the "improvement" or "regression" is conjecture.
