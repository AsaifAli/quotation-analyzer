# QuoteSense Security Review

This is a source/configuration assessment, not a production certification. Runtime, hosting and provider settings must also be verified.

## Present controls
- Bearer auth is enforced for analysis routes in `api_security.py`; an unset token fails closed.
- `app.py` checks auth before multipart parsing, bounds upload request bytes, and applies per-IP plus API-token-fingerprint quotas to protected analysis requests. In production, counters use Upstash REST Lua `EVAL` with an app-specific prefix; development uses a bounded in-process limiter (`api_rate_limit.py`). Production writes fail closed with 503 if Upstash is unavailable.
- `modules/document_processor.py` checks file extension and size.
- Extraction prompts treat supplier documents as untrusted data (`config.py`).
- CORS is configurable; Render blueprint no longer uses wildcard CORS.
- Gateway exchange uses a short-lived one-time code. Its bearer is kept in server-side Streamlit session state, not launch URLs. The exchange destination must match the configured approved HTTPS Gateway hostname and resolve only to public IPs; redirects are disabled.
- Provider keys are supplied as server-side deployment environment variables.
- No local password database, multi-tenant SQL database or webhook receiver is part of the identified app surface.

## Required before production
1. Replace the CORS origin in `render.yaml` with the actual production UI origin(s).
2. Configure unique high-entropy `API_AUTH_TOKEN` and provider keys in the hosting secret manager; rotate any exposed values.
3. Add malware scanning or isolated document parsing if the app is exposed to untrusted public uploads; signature/archive checks do not replace content scanning.
4. Add shared ingress/WAF rate limits as a second perimeter layer. The production application limiter is already shared through Upstash; the Render `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` environment values must be configured.
5. Restrict all URL-fetching integrations to configured HTTPS destinations; do not accept user-controlled URLs without SSRF protections.
6. Verify logs and error trackers do not capture uploads, extracted supplier fields, credentials or bearer tokens.
7. Run dependency scanning on the resolved deployment dependency set and patch high/critical findings.
8. Serve only over TLS. Streamlit session state is server-side and is not an HttpOnly browser cookie.

## 20-control assessment
| # | Control | Status |
|---|---|---|
|01|SQL injection|N/A — no app SQL database identified|
|02|XSS|PARTIAL — review all Streamlit Markdown/HTML rendering of untrusted extracted text|
|03|CSRF|PARTIAL — bearer-auth API reduces ambient-cookie CSRF; verify no cookie-auth routes|
|04|File upload|PARTIAL — extension/size and PDF/Office container signatures are validated; MIME sniffing/antivirus and deeper archive policy remain external hardening|
|05|SSRF|IMPROVED/PARTIAL — one-time Gateway handoff is pinned to an approved HTTPS public host; continue reviewing future URL-capable tools|
|06|BOLA/IDOR|N/A — no multi-user object API identified|
|07|Rate limiting|PARTIAL — per-IP and API-token-fingerprint counters are shared through Upstash in production; add ingress/WAF limits as a second layer|
|08|Password hashing|N/A — no local passwords|
|09|MFA|EXTERNAL — enable MFA on hosting/source-control/provider admin accounts|
|10|Server-side permissions|PARTIAL — bearer auth on analysis endpoints; no app roles|
|11|RLS|N/A — no tenant database identified|
|12|JWT secret|GATEWAY-OWNED — gateway validates signing key; confirm production secret rotation/TTL|
|13|Server-side API keys|PRESENT — Render env vars; never move private keys to frontend variables|
|14|Zero localStorage tokens|PARTIAL — gateway bearer held in server-side Streamlit state; verify browser storage|
|15|No default credentials|PARTIAL — no default login found; deployment tokens must be unique|
|16|Strict CORS|PATCHED — explicit `https://studio.asaifali-studio.workers.dev` origin in Render blueprint; synchronize if the production website hostname changes|
|17|Webhook signatures|N/A — no webhook receiver identified|
|18|Source maps|N/A — no browser JS build pipeline identified|
|19|Clean production logs|VERIFY — inspect runtime logs/error tracking for document/credential leakage|
|20|Dependency patching|UNVERIFIED — run scanner against resolved deployment environment|

## AI audit prompt
Act as a Principal Application Security Engineer. Audit all 20 controls. Mark each PASS, PARTIAL, FAIL or N/A; cite exact file and line references; explain exploitability; propose minimal tested patches. Do not infer a pass from absence of a code match. Separate code controls from hosting/provider actions and never print secret values.
