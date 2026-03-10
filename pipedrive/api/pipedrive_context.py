from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Optional

import httpx
from mcp.server.fastmcp import Context, FastMCP

from log_config import logger
from pipedrive.api.pipedrive_client import PipedriveClient
from pipedrive.pipedrive_config import (
    PIPEDRIVE_HEADER_API_TOKEN,
    PIPEDRIVE_HEADER_COMPANY_DOMAIN,
    PipedriveSettings,
    settings,
)

# Attribute name for request-scoped Pipedrive client (when using header credentials)
_REQUEST_STATE_PIPEDRIVE_CLIENT = "pipedrive_client"


@dataclass
class PipedriveMCPContext:
    pipedrive_client: Optional[PipedriveClient]


def get_pipedrive_context(ctx: Context) -> PipedriveMCPContext:
    """
    Resolve Pipedrive client for this request/session.
    - Over HTTP/SSE: credentials come only from request headers (X-Pipedrive-API-Token,
      X-Pipedrive-Company-Domain). No fallback to server env so that all secrets stay in
      the client (e.g. mcp.json).
    - Over stdio: use env-based client from lifespan if available.
    """
    request = getattr(ctx.request_context, "request", None)
    lifespan_ctx = ctx.request_context.lifespan_context
    default_client = lifespan_ctx.pipedrive_client if lifespan_ctx else None

    if request is not None and getattr(request, "headers", None) is not None:
        raw_token = request.headers.get(PIPEDRIVE_HEADER_API_TOKEN) or ""
        raw_domain = request.headers.get(PIPEDRIVE_HEADER_COMPANY_DOMAIN) or ""
        token = raw_token.strip() if isinstance(raw_token, str) else ""
        domain = raw_domain.strip() if isinstance(raw_domain, str) else ""
        if token and domain and len(token) >= 10 and "." not in domain:
            client = getattr(request.state, _REQUEST_STATE_PIPEDRIVE_CLIENT, None)
            if client is None:
                try:
                    header_settings = PipedriveSettings.from_headers(token, domain)
                    logger.info("Using client-supplied Pipedrive credentials for this request.")
                    async_client = httpx.AsyncClient(
                        timeout=header_settings.timeout,
                        verify=header_settings.verify_ssl,
                    )
                    client = PipedriveClient(
                        api_token=header_settings.api_token,
                        company_domain=header_settings.company_domain,
                        http_client=async_client,
                    )
                    setattr(request.state, _REQUEST_STATE_PIPEDRIVE_CLIENT, client)
                except ValueError:
                    pass
            if client is not None:
                return PipedriveMCPContext(pipedrive_client=client)
        raise ValueError(
            "Pipedrive credentials over HTTP/SSE must be sent via headers: "
            "X-Pipedrive-API-Token and X-Pipedrive-Company-Domain (no server-side fallback)."
        )

    if default_client is not None:
        return PipedriveMCPContext(pipedrive_client=default_client)

    raise ValueError(
        "Pipedrive credentials are required. For stdio: set PIPEDRIVE_API_TOKEN and "
        "PIPEDRIVE_COMPANY_DOMAIN in the environment. For HTTP/SSE: send "
        "X-Pipedrive-API-Token and X-Pipedrive-Company-Domain headers."
    )


@asynccontextmanager
async def pipedrive_lifespan(server: FastMCP) -> AsyncIterator[PipedriveMCPContext]:
    logger.info("Attempting to initialize Pipedrive MCP Context...")

    if settings is None:
        logger.info("No Pipedrive env config; credentials will be required via headers when using HTTP/SSE.")
        yield PipedriveMCPContext(pipedrive_client=None)
        return

    if not settings.verify_ssl:
        logger.warning("SSL verification is disabled. This should only be used in development environments.")

    async with httpx.AsyncClient(timeout=settings.timeout, verify=settings.verify_ssl) as client:
        pd_client = PipedriveClient(
            api_token=settings.api_token,
            company_domain=settings.company_domain,
            http_client=client,
        )
        mcp_context = PipedriveMCPContext(pipedrive_client=pd_client)
        try:
            logger.info("Pipedrive MCP Context initialized successfully.")
            yield mcp_context
        finally:
            logger.info("Pipedrive MCP Context cleaned up.")
