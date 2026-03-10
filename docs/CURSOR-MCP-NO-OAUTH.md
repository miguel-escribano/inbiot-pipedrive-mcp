# Cursor + remote MCP: header-only auth (no OAuth)

This MCP is intended to work with **header-only auth**: the client sends `X-MCP-Token`, `X-Pipedrive-API-Token`, and `X-Pipedrive-Company-Domain` on every request. No OAuth flow.

## How Cursor can connect

1. **Native remote (recommended)**  
   In `mcp.json`, use `url` and `headers`; no separate process. Cursor connects directly to the SSE URL with your headers. See README §4b.

2. **Via mcp-remote**  
   If you use `npx -y mcp-remote <url> --header "X-MCP-Token: ..." --header "X-Pipedrive-API-Token: ..." --header "X-Pipedrive-Company-Domain: ..."`, the first request is a GET to the SSE URL. The server **must return 200** when those headers are present and valid. If it returns 401, mcp-remote assumes OAuth and starts the browser/callback flow (which we don’t use for this server).

## Required server behavior

- **GET** (and SSE) to the MCP SSE path with headers `X-MCP-Token`, `X-Pipedrive-API-Token`, `X-Pipedrive-Company-Domain` → must return **200** and allow the SSE stream. Do not return 401 when these headers are valid.
- Nginx (and any Node bridge in front of the Python app) must forward these three headers to the upstream. The Python app reads Pipedrive credentials only from request headers over HTTP/SSE; see [HEADER_ONLY_DEPLOY.md](HEADER_ONLY_DEPLOY.md).

If you serve `/.well-known/oauth-authorization-server` for other MCPs, that’s fine. For this path, success depends on never returning 401 when the three headers are present and valid.

## EADDRINUSE (when using mcp-remote)

If you see `listen EADDRINUSE: address already in use 127.0.0.1:12940`, a previous mcp-remote run (or a 401 that triggered the OAuth callback server) left a process on that port. Kill it (Task Manager, or `netstat -ano` then `taskkill /PID <pid> /F`) or restart. Using native remote (`url` + `headers`) avoids mcp-remote and thus this issue.
