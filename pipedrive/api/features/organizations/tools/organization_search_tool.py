from typing import Optional, Dict, Any

from mcp.server.fastmcp import Context

from log_config import logger
from pipedrive.api.features.shared.conversion.id_conversion import convert_id_string
from pipedrive.api.features.shared.utils import format_tool_response, safe_split_to_list
from pipedrive.api.pipedrive_api_error import PipedriveAPIError
from pipedrive.api.pipedrive_context import PipedriveMCPContext, get_pipedrive_context
from pipedrive.api.features.tool_decorator import tool


MAX_SEARCH_PAGE_SIZE = 100
MAX_AUTO_PAGINATE_PAGES = 10


@tool("organizations")
async def search_organizations_in_pipedrive(
    ctx: Context,
    term: str,
    fields_str: Optional[str] = None,
    exact_match: bool = False,
    include_fields_str: Optional[str] = None,
    limit_str: Optional[str] = "100",
    cursor: Optional[str] = None,
    auto_paginate: bool = True,
) -> str:
    """
    Searches for organizations in the Pipedrive CRM by name, address, notes or custom fields.
    
    This tool searches across all organizations in Pipedrive using the provided term.
    Results can be filtered by specific fields to search in.
    
    Pagination:
    - Pipedrive search API returns max 100 results per page.
    - By default (auto_paginate=True), this tool automatically fetches all pages and returns
      the complete result set in a single call (up to 1000 results / 10 pages).
    - Set auto_paginate=False to get a single page and handle pagination manually via cursor.
    
    args:
    ctx: Context
    term: str - The search term to look for (min 2 chars, or 1 if exact_match=True)
    
    fields_str: Optional[str] = None - Comma-separated list of fields to search in (name, address, notes, custom_fields)
    
    exact_match: bool = False - When True, only exact matches are returned
    
    include_fields_str: Optional[str] = None - Comma-separated list of additional fields to include
    
    limit_str: Optional[str] = "100" - Results per page (max 100). With auto_paginate=True, this is the page size.
    
    cursor: Optional[str] = None - Pagination cursor for the next page (only used when auto_paginate=False)

    auto_paginate: bool = True - When True, automatically fetches all pages and returns complete results.
    """
    logger.debug(
        f"Tool 'search_organizations_in_pipedrive' ENTERED with raw args: "
        f"term='{term}', fields_str='{fields_str}', exact_match={exact_match}, "
        f"include_fields_str='{include_fields_str}', limit_str='{limit_str}', "
        f"cursor='{cursor}', auto_paginate={auto_paginate}"
    )

    if not term:
        error_message = "Search term cannot be empty"
        logger.error(error_message)
        return format_tool_response(False, error_message=error_message)
    
    if len(term) < 2 and not exact_match:
        error_message = "Search term must be at least 2 characters long when exact_match is False"
        logger.error(error_message)
        return format_tool_response(False, error_message=error_message)

    pd_mcp_ctx: PipedriveMCPContext = get_pipedrive_context(ctx)

    limit, limit_error = convert_id_string(limit_str, "limit")
    if limit_error:
        logger.error(limit_error)
        return format_tool_response(False, error_message=limit_error)
    if limit and limit > MAX_SEARCH_PAGE_SIZE:
        logger.warning(f"Search limit {limit} exceeds API max ({MAX_SEARCH_PAGE_SIZE}). Capping.")
        limit = MAX_SEARCH_PAGE_SIZE

    fields = safe_split_to_list(fields_str)
    include_fields = safe_split_to_list(include_fields_str)
    page_size = limit or MAX_SEARCH_PAGE_SIZE

    try:
        all_results = []
        current_cursor = cursor
        pages_fetched = 0

        while True:
            results, next_cursor = await pd_mcp_ctx.pipedrive_client.organizations.search_organizations(
                term=term,
                fields=fields,
                exact_match=exact_match,
                include_fields=include_fields,
                limit=page_size,
                cursor=current_cursor
            )
            all_results.extend(results)
            pages_fetched += 1

            if not auto_paginate or not next_cursor or pages_fetched >= MAX_AUTO_PAGINATE_PAGES:
                break
            current_cursor = next_cursor

        logger.info(
            f"Found {len(all_results)} organizations matching '{term}' "
            f"({pages_fetched} page(s), auto_paginate={auto_paginate})"
        )
        
        response_data = {
            "items": all_results,
            "next_cursor": next_cursor if not auto_paginate or pages_fetched >= MAX_AUTO_PAGINATE_PAGES else None,
            "count": len(all_results)
        }
        
        return format_tool_response(True, data=response_data)

    except PipedriveAPIError as e:
        logger.error(
            f"PipedriveAPIError in tool 'search_organizations_in_pipedrive' for term '{term}': {str(e)} - Response Data: {e.response_data}"
        )
        return format_tool_response(False, error_message=str(e), data=e.response_data)
    except Exception as e:
        logger.exception(
            f"Unexpected error in tool 'search_organizations_in_pipedrive' for term '{term}': {str(e)}"
        )
        return format_tool_response(
            False, error_message=f"An unexpected error occurred: {str(e)}"
        )