# Header-only credentials (no secrets on server)

When clients connect over HTTP/SSE (e.g. Cursor with `url` + `headers` in mcp.json), **all Pipedrive credentials must come from the request**. The server must not use env-based credentials for those requests.

## What we control (this repo)

- **`pipedrive_context.py`**: Over HTTP/SSE, credentials are taken **only** from request headers (`X-Pipedrive-API-Token`, `X-Pipedrive-Company-Domain`). No fallback to `PIPEDRIVE_*` env. If headers are missing or invalid, the app returns a clear error.
- **Stdio** (local run): still uses `PIPEDRIVE_API_TOKEN` and `PIPEDRIVE_COMPANY_DOMAIN` from the environment.

## What deploy / server must do

1. **Do not set** `PIPEDRIVE_API_TOKEN` or `PIPEDRIVE_COMPANY_DOMAIN` in the server environment for the inbiot-pipedrive-mcp service. That way the app never falls back to server-side (or placeholder) values.
2. **Forward headers** from the client to the Python app on every request. Nginx already has `proxy_set_header X-Pipedrive-API-Token` and `X-Pipedrive-Company-Domain` for this path. The Node SSE bridge (or whatever calls the Python app) must pass those headers through to the backend so the Python app sees them on `ctx.request_context.request.headers`.

After a push to GitHub and webhook redeploy, the new logic is live. No secrets on server; client keeps them in mcp.json.
