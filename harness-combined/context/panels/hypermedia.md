## Hypermedia & HTMX Panel

*Activation is governed by the trigger table in `skills/critique/SKILL.md`. Generic HTTP correctness (REST/OpenAPI, status codes, caching, content negotiation, versioning) lives in `http-api.md`; this panel covers the hypermedia layer on top.*

- **Carson Gross** — creator of HTMX; *Hypermedia Systems* (with Adam Stepinski and Deniz Akşimşek); hypermedia-driven architecture
- **Mark Nottingham** — IETF HTTPbis working group chair; HTTP semantics applied to hypermedia partials (Cache-Control on fragments, redirect vs. swap, Content-Type for partials). His broader HTTP positions live in `http-api.md`; here he is invoked where partial-response semantics differ from whole-resource semantics.

**Carson Gross's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Hypermedia as the engine of state** | The server controls application state through the HTML it returns — not through client-side logic or JSON payloads. An HTMX endpoint that returns data for the client to transform is doing it wrong. The response should be the transformed state, directly renderable. |
| **Partial responses must be self-consistent** | An HTMX swap target receives a fragment. That fragment must make sense on its own: correct IDs, correct ARIA relationships, correct HTMX attributes. A fragment that relies on surrounding DOM state it cannot see is fragile. |
| **HX-Redirect is a client-side redirect** | `HX-Redirect` triggers a full page navigation in the browser. It is appropriate after a state change that makes the current page stale (session start, step transition). Using it where `HX-Retarget` + a partial swap would suffice adds unnecessary page loads. |
| **HX-Retarget / HX-Reswap are escape valves** | Use them sparingly — when the HTMX attribute placement in the template can't express the swap target you need. Overuse is a sign the template structure is wrong. |
| **Out-of-band swaps (hx-swap-oob) for multi-target updates** | When a single action must update multiple disjoint areas of the DOM, include the secondary targets as `hx-swap-oob` elements in the response. Using JavaScript events or `HX-Trigger` to chain a second request is avoidable complexity. |
| **SSE for server-push** | Server-Sent Events are the right primitive for streaming AI responses — one-directional, simple, browser-native reconnect. The `htmx-ext-sse` extension wires them directly to HTMX swaps without JavaScript. When SSE is used, ensure events have named types so the extension can route them to the right target. |

**Mark Nottingham's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Status codes are contracts** | `200 OK` means the request succeeded and the response body is the resource. `204 No Content` means success with no body — HTMX will not swap on a 204, which is sometimes exactly right. `422 Unprocessable Entity` means the server understood the request but rejected it for validation reasons — correct for form errors. `500` is for server faults, not for "command failed." |
| **Location and redirect semantics** | A `303 See Other` after a POST is the correct pattern for PRG (Post-Redirect-Get). HTMX's `HX-Redirect` bypasses this — the response to the POST is already a redirect header, so the browser doesn't re-POST on reload. This is intentional, but understand what it replaces. |
| **Cache-Control on partial responses** | HTMX partial responses that should not be cached must carry `Cache-Control: no-store`. Browser and CDN caching of HTMX fragments causes state staleness that is extremely hard to debug. |
| **Content-Type precision** | `text/html` for HTML fragments. `text/event-stream` for SSE. `application/json` for JSON. Wrong Content-Type causes silent parse failures in browsers and HTMX. |
| **Header hygiene** | Custom headers (`HX-*`) are application-level protocol. They must not leak into responses that cross origin boundaries without appropriate CORS configuration. |

*Synthesis:* Gross evaluates whether the hypermedia architecture is coherent — whether the server is truly driving state through the HTML it returns. Nottingham (on this panel) evaluates whether the HTTP layer correctly handles the *partial-response* shape that hypermedia introduces: status codes that trigger or suppress swaps, cache-control on fragments, Content-Type for partials, header hygiene at origin boundaries. A response can be correct HTTP but wrong hypermedia (returns JSON where HTML was needed) or correct hypermedia but wrong HTTP (returns 200 for a validation error that should be 422). For generic HTTP design questions — REST constraints, versioning, contracts, problem+json — defer to `http-api.md`.

---

## Review Dimensions

---

### Dimension 12: Hypermedia Design
*Gross, Nottingham*

| Hazard | What to look for |
|--------|-----------------|
| **Wrong status code** | `500` for a user-facing failure that should be `422`; `200` returned when `204 No Content` would suppress an unwanted swap; `302` where `303 See Other` is the correct PRG pattern. |
| **Partial response not self-consistent** | An HTMX swap target fragment that relies on surrounding DOM state (IDs, ARIA relationships, HTMX attributes on ancestors) it cannot see. |
| **HX-Redirect overuse** | `HX-Redirect` triggers a full page navigation — used where a partial swap + `HX-Retarget` would suffice, adding unnecessary page loads. |
| **Missing cache control** | HTMX partial responses or SSE endpoints without `Cache-Control: no-store` where caching would cause state staleness. |
| **Wrong Content-Type** | HTML fragments must be `text/html`; SSE streams must be `text/event-stream`; JSON must be `application/json`. Wrong type causes silent parse failures. |
| **Response drives data, not state** | An HTMX endpoint returning JSON for the client to transform is incorrect hypermedia design. The response should be the rendered state fragment, directly swappable. |
| **Missing out-of-band swaps** | A single action updating multiple disjoint DOM regions, handled by chaining a second HTMX request via `HX-Trigger`, when `hx-swap-oob` in the response would be cleaner. |
| **SSE event naming** | SSE events without explicit `event:` type fields cannot be routed by `htmx-ext-sse` to specific targets. |
| **HX-* header CORS leakage** | Custom HX-* response headers on endpoints that might be accessed cross-origin without appropriate CORS configuration. |

Gross's design-level question: is the server truly driving application state through the HTML it returns, or is the client assembling state from data the server provides?
