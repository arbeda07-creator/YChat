# YChat Production Security Checklist

## Secrets and configuration

- [ ] Set `APP_ENV=production`.
- [ ] Set a unique, high-entropy `SECRET_KEY`; never reuse it across environments.
- [ ] Set `DATABASE_URL` to a TLS-protected production database account with least privilege.
- [ ] Set `REDIS_URL` to a private, authenticated Redis service reachable by every app instance.
- [ ] Keep `.env`, databases, logs, and `instance/uploads` outside source control and backups encrypted.
- [ ] Set `UPLOAD_FOLDER` to a private, non-executable persistent volume.
- [ ] Leave `TRUST_PROXY_HEADERS=false` unless exactly one trusted reverse proxy sits directly in front of YChat.

## HTTPS and reverse proxy

- [ ] Terminate TLS with a current certificate and redirect HTTP to HTTPS at the edge.
- [ ] If proxy trust is enabled, strip client-supplied `Forwarded`/`X-Forwarded-*` headers before setting authoritative values.
- [ ] Confirm `Secure`, `HttpOnly`, and `SameSite=Lax` on `ychat_session` in a production browser.
- [ ] Confirm HSTS is emitted only on HTTPS and account for subdomains before enabling preload.
- [ ] Restrict upload/body size at both the proxy and application layers.

## Runtime and data

- [ ] Run as an unprivileged OS user with read-only application code.
- [ ] Permit write access only to the private upload and required runtime directories.
- [ ] Confirm startup fails when production Redis is unavailable and verify rate-limit counters across instances.
- [ ] Run `flask import-json-messages`, verify history, then run it with `--delete-originals` and retain `.bak` files until backups are validated.
- [ ] Back up and restore-test the database and private uploads.
- [ ] Protect logs from tampering and configure retention without recording message bodies, cookies, or tokens.

## Verification

- [ ] Run `python -m unittest discover -s tests -v`.
- [ ] Run `python -m pip check` and a dependency vulnerability scanner in CI.
- [ ] Test CSRF, authorization, upload validation, CSP, logout, and idle expiry through the deployed proxy.
- [ ] Monitor failed-login, CSRF-rejection, rate-limit, and private-upload-denial events.
- [ ] Rotate secrets after suspected exposure and invalidate all sessions by rotating `SECRET_KEY`.
