# nginx — TLS termination and the only published port

## Purpose

Reverse proxy in front of the Flask app: publishes 80/443, terminates TLS, and is the only host that puts the public hostname and scheme into the request the app sees.

## Ownership

- `nginx.conf` (56 lines) — the entire config: `client_max_body_size` at `http` level, the `opennourish_app` upstream, and one server block per port. Refer to directives by name, never by line number.
- `Dockerfile` — `nginx:1.29` plus `openssl` (the entrypoint needs it), the config copied over the distro default, the custom entrypoint.
- `entrypoint.sh` — certificate resolution at container start: symlink real certs, or generate a self-signed pair.
- Not owned here: the compose service definition, image tags, volumes, and published ports (`/docker-compose.yml`, root); how the app interprets forwarded headers (`opennourish/AGENTS.md`, and root's `TRUSTED_PROXY_HOPS` contract).

## Local Contracts

- `client_max_body_size 10m` sits at `http` level, so both server blocks inherit it, and it is the **only body cap in the stack** — the app sets no `MAX_CONTENT_LENGTH`. At nginx's 1 MiB default the YAML food and recipe importers were answered with 413 before the request ever reached Flask. Never drop the directive or move it under a single `location`.
- The app is reached by service name (`opennourish-app:8081`) and this is the only service that publishes ports. Nothing else may expose :8081 — the app only trusts one proxy hop, so a directly reachable socket lets a client choose the host and scheme written into password-reset links.
- The proxy headers are load-bearing, not decoration: `Host` and `X-Forwarded-Host` from `$http_host` decide the host baked into `url_for(..., _external=True)` (verification and password-reset links), and `X-Forwarded-Proto` decides the scheme. The HTTP block hardcodes `http` for it; the TLS block passes `$scheme`. Keep both.
- **No `Referrer-Policy` header is sent, deliberately.** Flask-WTF keeps `WTF_CSRF_SSL_STRICT` at its True default, which checks the `Referer` on HTTPS POSTs; a `no-referrer` (or origin-stripping) policy removes the header Flask-WTF needs and 400s every HTTPS form.
- Certificates: `entrypoint.sh` symlinks `$REAL_CERT_PATH` / `$REAL_KEY_PATH` into `/etc/nginx/certs/{fullchain.pem,privkey.pem}` when both are set and both files exist; otherwise it generates a self-signed pair (`CN=opennourish-selfsigned`, RSA-4096, 365 days) only if none is present. Compose mounts `./persistent/nginx_certs` at that path, so a generated pair survives restarts — switching to real certificates means replacing the pair or setting the two variables, not just redeploying.
- Both server blocks use the catch-all `server_name _`. There is no vhost selection here, so the client's Host header travels to the app unchanged — which is why the app validates redirect targets against `request.host` (root Security).
- TLS floor: TLSv1.2 and 1.3 only, with an explicit AEAD-first cipher list.

## Work Guidance

- Anything added inside `http {` applies to both ports; anything inside one `server` applies to one. `add_header` does not inherit into a child block that declares its own, so a header added to the TLS block is silently absent on plain HTTP — say so in the commit if that is the intent.
- Config changes are validated before deploy with the command below; the upstream host mapping and the generated certs are what let `-t` pass outside the compose network.

## Verification

```bash
docker run --rm --add-host opennourish-app:127.0.0.1 \
  -v "$PWD/nginx/nginx.conf":/etc/nginx/nginx.conf:ro \
  nginx:1.29 nginx -t
```

The image's entrypoint runs first and creates the self-signed pair `nginx -t` must be able to read; `--add-host` satisfies the upstream lookup.

## Child DOX Index

No child docs.
