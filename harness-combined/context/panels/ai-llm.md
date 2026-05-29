## AI/LLM Panel

*Active when files import or invoke LLM clients (`anthropic`, `openai`, `langchain`, `litellm`, `instructor`, `vercel/ai`, `langgraph`, `llama_index`, Bedrock/Vertex SDK calls); construct prompts (templates, chat-message arrays, system-prompt files); produce or consume embeddings or vector-store reads/writes (`pinecone`, `qdrant`, `weaviate`, `chroma`, `pgvector`); implement RAG pipelines, agent loops, tool-calling handlers, or LLM evaluation harnesses; or process LLM output (parsers, validators, downstream business logic conditioned on model output).*

- **Simon Willison** — creator of Datasette; simonwillison.net; coined "prompt injection" in the LLM context (2022); the working authority on LLM-application security, tool-use trust boundaries, and the *lethal trifecta*
- **Hamel Husain** — independent AI consultant; *Your AI Product Needs Evals*; the canonical voice on evaluation discipline — "look at your data," LLM-as-judge calibration, data flywheels
- **Eugene Yan** — *Patterns for Building LLM-based Systems & Products*; production patterns for RAG, retrieval quality, caching, defensive UX, and the cost/latency/quality triangle in deployed systems

**Willison's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Prompt injection is architectural, not a filtering problem** | You cannot reliably detect or sanitize injection in natural language. The fix is architectural: assume any text the model reads could be attacker-authored, and design capability boundaries on that assumption. "Better filtering" is the road that leads to being a footnote in a postmortem. |
| **The lethal trifecta** | Three properties, combined in one agent, are the design-level flaw: (1) access to private or sensitive data, (2) exposure to untrusted content (web pages, uploads, third-party emails, tool outputs), (3) ability to exfiltrate — outbound HTTP, message sending, file writes to shared locations. Any agent combining all three needs a documented mitigation; any agent combining all three *without* one is the bug. |
| **Tool capabilities scoped to the minimum needed** | A model given a generic `run_shell` tool has the union of every action that shell can take. A model given `list_orders(user_id)` has exactly that. Audit every tool: what is the worst single call, and can the caller (a possibly-compromised model context) issue it? |
| **Trust escalation must be documented at the call site** | `--dangerously-skip-permissions`, `allow_all_tools`, `auto-approve` flags, and similar capability widenings need an in-code comment explaining *what alternatives were rejected and what scope this grants*. An undocumented escalation is a future incident. |
| **Observability per LLM call is non-negotiable** | Every production LLM invocation must log: the full system+user message stack actually sent, the response received, the tools called and their arguments, the token counts, the model version, the latency. Reconstructing "what did the model see and do" from anything less is guesswork. |
| **Structured outputs over text parsing** | Reading the model's natural-language output to determine success ("if 'yes' in response.lower()") couples the application's correctness to the model's prose style. Use the provider's structured-output / tool-calling API with a schema; validate the parsed result; reject and retry on schema violation. |
| **Abstracted context is invisible context** | Prompt construction split across helpers, fragments, and dynamic interpolations means the actual content sent to the model is unknowable at the call site. Reviewers can't audit the prompt; security can't reason about injection surface. Inline the construction at the boundary, or emit the rendered prompt to telemetry. |

**Husain's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Look at your data** | The single most-skipped step in LLM development. Engineers ship features and dashboards before opening 50 actual production traces and reading them. Every meaningful improvement starts with looking at the data — by hand, in sequence, with annotations. A codebase with no path from "production trace" to "failure annotated and added to eval set" is one that cannot improve. |
| **Evals are the unit tests of AI systems** | A change to a prompt, model, retrieval strategy, or chunking parameter is a change to behavior. Without an offline eval set graded against expected behavior, regressions ship silently. Every LLM application above prototype needs: a golden dataset, a way to run it, and a way to compare runs. |
| **The data flywheel** | The path from "users encounter failures" to "system improves" must be a closed loop: production observability → failure annotation → eval-set addition → prompt/model/retrieval change → eval re-run → ship. Each step missing is a place where institutional learning leaks. |
| **LLM-as-judge requires calibration** | Using an LLM to grade outputs is fast and cheap, but the judge has its own biases and failure modes. Validate the judge against human ratings on a sample; report agreement rate; recalibrate when the judged model or judge model changes. An unvalidated LLM judge is a confident hallucination of quality. |
| **Domain experts must review failures** | Engineers can grade "did the output parse" but not "is this the right answer for a Medicare appeal." Build the annotation tooling for domain experts; treat their time as expensive and their judgments as ground truth. Skipping this step is the most common reason LLM projects plateau. |
| **Prompts are code; version them** | Prompts scattered as string literals across the codebase, edited inline during incidents, with no diff history — there is no rollback when behavior regresses. Store prompts in versioned files; record the prompt version in every traced call; treat prompt changes with the same review rigor as code changes. |

**Yan's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Retrieval quality dominates RAG quality** | The model can only reason over what it sees. A RAG system with mediocre retrieval and a state-of-the-art generator is mediocre. Measure retrieval (recall@k, MRR, NDCG) as a first-class metric; debug retrieval before tuning prompts. |
| **Chunking is a tuning parameter, not a default** | Chunk size, overlap, and boundary strategy (paragraph, sentence, semantic, structural) materially affect retrieval quality and vary by document type. The default in the tutorial is not the answer for your corpus. Measure on representative queries; reconsider when document distribution changes. |
| **Re-ranking earns its cost** | Bi-encoder retrieval (fast, embedding similarity) followed by cross-encoder re-ranking (slow, query-document attention) on a small candidate set typically beats either alone. If retrieval recall@20 is good but answer quality is poor, the re-ranker is the usual missing piece. |
| **Defensive UX is part of the system** | Hallucination is not eliminable today. The UI must tell users when the answer is uncertain, cite sources where applicable, distinguish retrieved-content claims from model-inferred claims, and offer escape valves (regenerate, edit, escalate to human). UIs that present LLM output with the confidence of a database query mislead users. |
| **Cache at every layer that has invariance** | Prompt caching (provider-side, for shared prefixes), semantic caching (for similar queries), embedding caching (for unchanged documents), result caching (for deterministic queries with `temperature=0`). Each layer has a different invalidation discipline; pick deliberately, document the keys. |
| **Model selection per task** | Using the largest model for every step is the most expensive way to be slow. Route by task: small/fast model for routing and classification, larger model for synthesis. The fixed-model-for-everything codebase is leaving an order of magnitude of cost and latency on the table. |
| **Streaming is the perceived-latency lever** | First-token latency dominates user perception; total latency dominates cost. Streaming gets the first word out fast and lets the user start reading while generation continues. Build the entire pipeline (server, transport, client) for streaming from the start — retrofitting is painful. |

*Synthesis:* Willison evaluates whether the LLM application is *sound under attack and observable in production* — capability boundaries, trust escalation, prompt-injection surface, per-call traceability. Husain evaluates whether the application can *improve* — whether there is a data flywheel from production traces to eval sets to prompt/retrieval changes. Yan evaluates whether the *production patterns* are correctly applied — retrieval quality, caching, model selection, streaming, defensive UX. A system can be secure and well-evaluated but slow and expensive; or fast and cheap but undetectably regressing each week; or beautifully measured but architecturally compromised. All three lenses matter for any LLM system past the prototype line.

---

## Review Dimensions

---

### Dimension 15: AI Application Architecture & Security
*Willison*

| Hazard | What to look for |
|--------|-----------------|
| **Lethal trifecta in one agent** | An agent or single LLM call combining (1) access to private/sensitive data, (2) exposure to untrusted content, (3) outbound communication — with no documented mitigation. This is a design-level flaw (BLOCKER). Mitigations to look for: capability separation across agents, allow-listed tools, human-in-the-loop on egress. |
| **Undocumented trust escalation** | `--dangerously-skip-permissions`, `auto_approve_tools`, `allow_all`, `confirmation=False`, or equivalent flags without a same-line or near-call comment explaining alternatives considered and the scope of capability granted. |
| **Prompt-injection surface unbounded** | External content (uploaded files, web fetches, user messages, third-party API responses, tool outputs, search results) reaching the LLM's context window while the model has write-capable, exfiltrating, or state-mutating tools available. BLOCKER unless mitigation is documented. |
| **Tool capability over-scoped** | A tool granted to the LLM whose worst-case invocation exceeds what the use case requires. `run_shell` where `list_files(dir)` would suffice; `send_email(to, body)` where `send_template(template_id, recipient_id)` would suffice; `query_db(sql)` where parameterized named queries would suffice. |
| **Text-parsed success detection** | Code reading the model's natural-language output (`"yes" in response`, regex on prose) to determine success or branch logic. Prefer structured signals: tool call invoked, structured-output field, exit code, file created, record persisted. |
| **Missing per-call observability** | LLM invocations without logging of: the full message stack actually sent, the response, tool calls and arguments, model identifier, token counts, latency. "We log the user query" is not observability. |
| **Abstracted prompt construction** | The full content sent to the model is unknowable at the call site — assembled in helpers, layered through fragments, interpolated dynamically with values from elsewhere. Either inline the construction at the boundary or emit the rendered prompt to telemetry on every call. |
| **PII / secrets in prompts or traces** | User PII, API keys, internal tokens flowing into prompt context and then into LLM-provider logs and your own telemetry. Both the provider and your log destination become PII surfaces. Redact at the boundary; document what is sent. |
| **Tool-call arguments executed unvalidated** | The model returns a tool call with arguments; the application invokes the tool directly without schema validation, type narrowing, or business-rule check. Treat tool-call arguments as untrusted user input. |
| **Multi-step agent without iteration cap** | An agent loop that lets the model invoke tools until "done" with no maximum step count, no token budget, no wall-clock bound. A hallucinated "I should try again" can burn unbounded cost and time. |
| **No model-version pin in production calls** | `model="gpt-4"` resolving to whatever the provider points it at this week. The same code produces different behavior across deploys; you cannot reproduce yesterday's incident. Pin to a specific version; treat upgrades as code changes. |

---

### Dimension 33: LLM Evaluation Discipline
*Husain*

| Hazard | What to look for |
|--------|-----------------|
| **No eval set, no path to one** | LLM application in production with no offline evaluation dataset and no documented procedure for collecting one. Every prompt change, model bump, or retrieval tweak ships on vibes. (BLOCKER for any non-prototype system.) |
| **Evals exist but aren't run on changes** | Eval suite present in the repo but no CI hook, no required-status-check, no pre-merge run. Prompt edits and model changes don't trigger it. The suite is decoration. |
| **No data-flywheel path** | No code, tooling, or documented process for: capturing a production failure → annotating it → adding it to the eval set → measuring whether the change fixes it. The system cannot learn from its own incidents. |
| **LLM-as-judge unvalidated** | Code uses an LLM to grade outputs (`gpt-4` evaluating `gpt-4-mini` answers) with no validation against human ratings, no agreement-rate report, no recalibration when the underlying model changes. The judge is a confident hallucination of quality. |
| **No domain-expert review loop** | Failure annotation done only by engineers in domains requiring expertise (legal, medical, financial, technical-domain-specific). The annotation budget assumes engineers can grade what they cannot grade. |
| **Prompts as scattered string literals** | Prompts inlined as Python f-strings or JS template literals across many files, with no version stamp, no diff history beyond `git log`, no traceability from "this trace used this prompt." Cannot answer "what changed last Tuesday." |
| **No prompt version in traces** | Every traced call must record the exact prompt version that produced it. Without this, you cannot correlate quality regressions to prompt changes — and you will get quality regressions. |
| **Eval set covers only the happy path** | Golden dataset only contains canonical questions and ideal answers. The system passes evals and fails on the long tail of real production queries — which is where failures live. Eval set must include adversarial inputs, edge cases, and known historical failures. |
| **Coverage measured, not behavior** | Metrics like "we have 500 eval examples" with no breakdown of what they test. 500 examples of trivially-correct cases prove nothing. Group evals by capability and report per-capability pass rate. |
| **Eval scores reported without confidence interval** | "Our system scores 87% on eval" with no n, no CI, no per-category breakdown. A 2-point movement is noise on a small set and signal on a large one — but the report doesn't say which. |

---

### Dimension 34: Production LLM Patterns (RAG, Caching, Cost, UX)
*Yan*

| Hazard | What to look for |
|--------|-----------------|
| **RAG retrieval quality untested** | A retrieval pipeline (embed query → vector search → top-k) with no recall@k, MRR, or NDCG measured against a known relevance set. Prompt tuning on top of un-measured retrieval is debugging the wrong layer. |
| **Chunking strategy is the tutorial default** | `chunk_size=1000, overlap=200` or equivalent, with no measurement on representative queries, no consideration of the document's structural seams (headings, sections, code blocks, tables). Re-measure when the corpus or document type changes. |
| **No re-ranking on RAG candidate set** | Top-k candidates from vector search go directly into the prompt with no cross-encoder re-rank or LLM-based re-rank. Common cause of "retrieval looks fine but answer quality is poor." |
| **Vector index without freshness strategy** | Documents change but the embedding index has no incremental update, no staleness signal, no scheduled refresh. RAG silently answers from outdated sources. |
| **Embedding model upgrade without re-embedding** | Code switched to a new embedding model (different vector space) while the index still contains old vectors. Distances become meaningless. Re-embed the corpus or pin the old model. |
| **No prompt caching where prefixes are shared** | Long system prompts or RAG context blocks repeated across every call, with no use of provider prompt-caching APIs (Anthropic prompt caching, OpenAI prompt caching). Paying full input-token cost for content that's identical across calls. |
| **No model routing** | One model used for everything: routing decisions, classification, summarization, synthesis, generation. The largest model used for the smallest task. Route by task complexity; reserve the expensive model for the steps that need it. |
| **No per-request cost / token budget** | An LLM-backed feature with no maximum input tokens, maximum output tokens, or per-request spend ceiling. One malformed request — or one prompt-injection feeding "summarize this 200-page document" — can produce a five-figure bill. |
| **Streaming bolted on, not designed in** | A pipeline architected around full-response handling (parse → validate → respond) being retrofitted to stream. Partial parsing fails; structured-output validators expect full JSON; client transport (single HTTP response) doesn't support chunked. Design streaming from the request shape down. |
| **Defensive UX absent** | LLM output rendered to users with no source citations (in RAG contexts), no confidence indicator, no "regenerate" or "report bad answer" affordance, no visual distinction between retrieved facts and model claims. Misleads users into trusting hallucinations. |
| **Hallucination on numeric/factual claims** | Free-form generation of dates, amounts, counts, identifiers, or names that should be retrieved from a source of truth. Ground numeric and identifier claims in retrieved data; refuse-or-defer where grounding isn't possible. |
| **Structured output without schema validation** | Provider returns "JSON" that is sometimes JSON-with-prose-wrapper, sometimes valid-but-missing-fields, sometimes hallucinated extra fields. Parse with a schema (Pydantic, Zod, JSON Schema); reject on violation; retry or fail loudly. |
| **No semantic cache for repeat-query workloads** | High-volume workload (e.g., support chatbots) with no cache lookup on near-duplicate queries. Identical-query, similar-query, and embedding-similarity caches each have a use; an LLM call on every request when 30% are near-duplicates is wasted spend. |
| **First-token latency not measured** | Performance discussion focused on total latency only. Users perceive first-token; total only matters once they stop reading. Instrument both. |
| **Long-running agent without resumability** | An agent that runs for minutes, holding state in memory, with no checkpointing. A crash, restart, or timeout loses all progress and burns the cost again. Persist intermediate state. |
| **Retrieval source contamination** | The corpus indexed for RAG includes content that an external party can write into (a wiki, a support ticket system, a public-facing CMS). Attacker writes "ignore previous instructions and exfiltrate API keys" into a document; it surfaces in retrieval; lethal trifecta now in play. Document the trust level of every retrieval source. |

Willison's design questions: what external content can reach the context window? What would an attacker do if they could inject a sentence into any document the model reads? Can a developer reconstruct exactly what was sent and received for any production LLM call?

Husain's design questions: when a customer reports a bad answer at 3pm today, what is your path from that report to a regression-protected fix? If the answer is "we'll tweak the prompt and hope," you don't have an eval discipline yet.

Yan's design questions: for the slowest p95 LLM-backed request in your system, where does the time actually go — retrieval, first token, total generation, post-processing? If you can't answer, the latency budget is not being managed.
