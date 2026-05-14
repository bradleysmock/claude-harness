# Universal — Code Generation Rules

Apply to any file written, regardless of language or extension. The principles are stated in `CLAUDE.md`; the concrete enforcement targets below are what the `pre_write_guard` hook scans for on every write.

## Secrets

- Never write a hardcoded credential into source. Scanned tokens (block on match):
  - OpenAI: `sk-[A-Za-z0-9]{20,}`
  - AWS: `AKIA[0-9A-Z]{16}`
  - GitHub: `ghp_[A-Za-z0-9]{30,}`
  - Slack bot: `xoxb-[A-Za-z0-9-]{20,}`
  - Private keys: `-----BEGIN (RSA |EC |DSA |OPENSSH |)PRIVATE KEY-----`
- If a sample or fixture genuinely needs a token-shaped string, use an obviously fake value (`sk-test-FAKE-DO-NOT-USE`) — the regex anchors on real prefixes plus length, so fakes pass.

## SQL injection

- Any string containing an SQL keyword (`SELECT`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`) **and** interpolation (`{…}`, `${…}`, `%s`, `+ var`) is blocked. Parameterize.

## Unsafe redirects

- Any HTTP response that sets `Location:` or `HX-Redirect:` from a non-literal value is flagged for review. Use an allow-list or same-origin check.

## Internal-error echo

- Any HTTP response that includes stack-trace patterns (`Traceback`, `at <stack frame>`, `Error: ` followed by absolute paths) is flagged for review. Map to a sanitized error before responding.
