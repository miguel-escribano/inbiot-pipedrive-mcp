"""Tests for pipedrive_context: get_pipedrive_context header path and fallback."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pipedrive.api.pipedrive_context import PipedriveMCPContext, get_pipedrive_context
from pipedrive.api.pipedrive_client import PipedriveClient


def test_get_pipedrive_context_uses_lifespan_when_no_request():
    """When context has no HTTP request, uses lifespan_context client."""
    mock_client = MagicMock(spec=PipedriveClient)
    mock_ctx = MagicMock()
    mock_ctx.request_context.request = None
    mock_ctx.request_context.lifespan_context = PipedriveMCPContext(
        pipedrive_client=mock_client
    )

    result = get_pipedrive_context(mock_ctx)

    assert result.pipedrive_client is mock_client


def test_get_pipedrive_context_raises_when_no_credentials():
    """When no lifespan client and no valid headers, raises clear error."""
    mock_ctx = MagicMock()
    mock_ctx.request_context.request = None
    mock_ctx.request_context.lifespan_context = PipedriveMCPContext(
        pipedrive_client=None
    )

    with pytest.raises(ValueError) as excinfo:
        get_pipedrive_context(mock_ctx)

    assert "Pipedrive credentials are required" in str(excinfo.value)
    assert "X-Pipedrive" in str(excinfo.value)


def test_get_pipedrive_context_uses_headers_when_both_present():
    """When request has both X-Pipedrive headers, builds client from headers."""
    mock_ctx = MagicMock()
    mock_request = MagicMock()
    mock_request.headers.get.side_effect = lambda k: {
        "X-Pipedrive-API-Token": "test_token_12345678901234567890",
        "X-Pipedrive-Company-Domain": "mycompany",
    }.get(k, "")
    # Use SimpleNamespace so getattr(state, 'pipedrive_client', None) returns None and setattr works
    mock_request.state = SimpleNamespace()
    mock_ctx.request_context.request = mock_request
    mock_ctx.request_context.lifespan_context = PipedriveMCPContext(
        pipedrive_client=None
    )

    result = get_pipedrive_context(mock_ctx)

    assert result.pipedrive_client is not None
    assert result.pipedrive_client.base_client.api_token == "test_token_12345678901234567890"
    assert result.pipedrive_client.base_client.domain == "https://mycompany.pipedrive.com"
