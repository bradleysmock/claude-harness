## AI/LLM Panel

*Active when `app/clients/**` files are in scope or when the code under review constructs prompts, invokes LLMs, or processes LLM output.*

- **Simon Willison** — creator of Datasette, simonwillison.net; coined "prompt injection" in the LLM context; AI application design and observability

---

## Review Dimensions

---

### Dimension 15: AI Application Design
*Willison*

| Hazard | What to look for |
|--------|-----------------|
| **Undocumented trust escalation** | `--dangerously-skip-permissions` or equivalent without a comment explaining the trust decision, alternatives considered, and scope of capability granted. |
| **Prompt injection surface** | External content (uploaded files, user messages, web data) reaching the LLM's context window while the model has write-capable or side-effecting tools available. |
| **Text-parsed success detection** | Code reading the LLM's natural-language output to determine success. Prefer structured signals: exit code, file written, record created. |
| **Missing observability** | LLM invocations without logging: (a) what was sent, (b) what was received, (c) what tool calls were made. |
| **Unbounded tool capabilities** | LLM given write access when read-only would suffice. |
| **Abstracted context content** | Prompt construction hidden in helpers that make the full content sent to the model invisible at the call site. |

Willison's design questions: what external content can reach the context window? What would an attacker do if they could inject a sentence into any document the model reads? Can a developer reconstruct exactly what was sent and received for any production LLM call?
