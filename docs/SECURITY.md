# Security notes

## Implemented

- **Authentication:** username/password (scrypt, per-user salt) → HMAC-SHA256 signed expiring bearer tokens.
  Roles viewer/operator/admin enforced per endpoint (tests cover 401/403 paths).
- **Device auth:** random 256-bit tokens shown once; only SHA-256 hashes stored; rotation and deletion revoke.
  Devices can only see/ack their own commands.
- **Uploads:** extension + declared MIME allowlist, size limit enforced while reading, full decode with
  decompression-bomb guard, real format check, min/max dimensions, server-generated filenames, re-encoding
  to JPEG (strips EXIF/GPS and trailing payloads), path-traversal-safe image serving behind auth.
- **Errors:** uniform envelope; stack traces and exception messages never reach clients (tested); request IDs.
- **CORS:** explicit allowlist; wildcard rejected in production; no cookies (`allow_credentials=false`).
- **Secrets:** only via environment; `.env`, firmware `config.h` git-ignored; `.env.example` has placeholders.
  The Mongo URI is never logged.
- **Production guards:** `ENVIRONMENT=production` refuses to start without a ≥32-char `SECRET_KEY`, a
  non-default `ADMIN_PASSWORD`, and a non-wildcard CORS list.
- **Rate limiting:** in-process sliding window for login (10/min/IP), password change, uploads (30/min/user)
  and device calls (240/min/device).
- **Logging:** structured JSON with UTC timestamps, level, request ID; passwords/tokens never logged.
  Audit log of operator actions, decisions, commands and safety events (TTL retention).
- **Idempotency & concurrency:** device scan uploads (Idempotency-Key), command ack/result, atomic device
  lock against overlapping sprays, optimistic concurrency on policy updates.

## Known trade-offs (prototype scope)

- The dashboard stores the bearer token in `localStorage` (XSS would expose it). Next.js escapes output and
  no `dangerouslySetInnerHTML` is used. For production, move to an httpOnly cookie via a same-origin proxy.
- The rate limiter is per-process. Behind multiple instances use the reverse proxy (e.g. nginx
  `limit_req`) or a shared store.
- The development admin password `agriguard-dev` exists **only** when `ADMIN_PASSWORD` is unset and never in
  production. The UI shows a warning while it is in use.
- Without `SECRET_KEY`, dev tokens are signed with a random per-process key (sessions end on restart).

## Deployment checklist

1. `ENVIRONMENT=production`, strong `SECRET_KEY`, `ADMIN_PASSWORD`, `CORS_ORIGINS` = your dashboard origin.
2. Atlas: dedicated project, least-privilege DB user, IP allowlist (no permanent `0.0.0.0/0`).
3. Terminate TLS at a reverse proxy; devices use HTTPS; add proxy rate limits.
4. Change the admin password at first login; create individual operator accounts.
5. Keep `uploads/` on persistent storage and review `UPLOAD_RETENTION_DAYS` for privacy.
6. Do not upload private farm images to third-party services without consent.
