from typing import Optional

from mcp.server.fastmcp import Context

from log_config import logger
from pipedrive.api.features.shared.conversion.id_conversion import convert_id_string
from pipedrive.api.features.shared.utils import format_tool_response
from pipedrive.api.pipedrive_api_error import PipedriveAPIError
from pipedrive.api.pipedrive_context import PipedriveMCPContext, get_pipedrive_context
from pipedrive.api.features.tool_decorator import tool

MAX_SEARCH_PAGE_SIZE = 100
MAX_AUTO_PAGINATE_PAGES = 10


@tool("deals")
async def search_deals_in_pipedrive(
    ctx: Context,
    term: str,
    fields_str: Optional[str] = None,
    exact_match: bool = False,
    person_id_str: Optional[str] = None,
    organization_id_str: Optional[str] = None,
    status: Optional[str] = None,
    include_fields_str: Optional[str] = None,
    limit_str: Optional[str] = "100",
    cursor: Optional[str] = None,
    auto_paginate: bool = True,
) -> str:
    """Searches for deals in the Pipedrive CRM by title, notes or custom fields.

    This tool performs a full-text search across deals in Pipedrive using the provided search term.
    The search can be focused on specific fields and filtered by person, organization, and status.

    Pagination:
    - Pipedrive search API returns max 100 results per page.
    - By default (auto_paginate=True), this tool automatically fetches all pages and returns
      the complete result set in a single call (up to 1000 results / 10 pages).
    - Set auto_paginate=False to get a single page and handle pagination manually via cursor.
    
    Format requirements:
    - term: Required search text (minimum 2 characters, or 1 character with exact_match=True)
    - fields_str: Optional comma-separated list of fields to search in (defaults to all searchable fields)
    - person_id_str, organization_id_str: Optional numeric ID strings (e.g. "123")
    - status: Optional filter by status ("open", "won", or "lost")
    - limit_str: Results per page (1-100, default 100). With auto_paginate=True, this is the page size.
    
    Search Fields:
    You can specify which fields to search in with the fields_str parameter:
    - "title": Search in deal titles only
    - "notes": Search in deal notes only
    - "custom_fields": Search in custom fields only
    - Leave empty to search in all searchable fields
    
    Search Behavior:
    - By default, performs a partial match search (matches terms within words)
    - With exact_match=True, only complete word matches are returned
    - Searches are case-insensitive
    - Only searchable custom field types are included: address, text, varchar, numeric, phone
    
    Filtering:
    - person_id_str: Find deals associated with a specific person
    - organization_id_str: Find deals associated with a specific organization
    - status: Filter to only "open", "won", or "lost" deals
    
    Example usage:
    ```
    search_deals_in_pipedrive(
        term="software license",
        fields_str="title,notes",
        status="open",
        organization_id_str="123"
    )
    ```

    args:
    ctx: Context
    term: str - The search term to look for (min 2 chars, or 1 if exact_match=True)
    fields_str: Optional[str] = None - Comma-separated list of fields to search in ("title", "notes", "custom_fields")
    exact_match: bool = False - When True, only exact matches are returned
    person_id_str: Optional[str] = None - Filter deals by person ID
    organization_id_str: Optional[str] = None - Filter deals by organization ID
    status: Optional[str] = None - Filter deals by status ("open", "won", "lost")
    include_fields_str: Optional[str] = None - Comma-separated list of additional fields to include
    limit_str: Optional[str] = "100" - Results per page (1-100)
    cursor: Optional[str] = None - Pagination cursor (only used when auto_paginate=False)
    auto_paginate: bool = True - When True, automatically fetches all pages and returns complete results.
    """
    logger.debug(
        f"Tool 'search_deals_in_pipedrive' ENTERED with raw args: "
        f"term='{term}', fields_str='{fields_str}', "
        f"exact_match={exact_match}, person_id_str='{person_id_str}', "
        f"organization_id_str='{organization_id_str}', status='{status}', "
        f"include_fields_str='{include_fields_str}', limit_str='{limit_str}', "
        f"cursor='{cursor}', auto_paginate={auto_paginate}"
    )
    
    if not term or not term.strip():
        error_message = "Search term cannot be empty"
        logger.error(error_message)
        return format_tool_response(False, error_message=error_message)
    
    term = term.strip()
    if not exact_match and len(term) < 2:
        error_message = "Search term must be at least 2 characters long (or 1 if exact_match=True)"
        logger.error(error_message)
        return format_tool_response(False, error_message=error_message)

    fields_str = None if fields_str == "" else fields_str
    person_id_str = None if person_id_str == "" else person_id_str
    organization_id_str = None if organization_id_str == "" else organization_id_str
    status = None if status == "" else status
    include_fields_str = None if include_fields_str == "" else include_fields_str
    cursor = None if cursor == "" else cursor

    pd_mcp_ctx: PipedriveMCPContext = get_pipedrive_context(ctx)

    try:
        page_size = MAX_SEARCH_PAGE_SIZE
        if limit_str:
            try:
                page_size = int(limit_str)
                if page_size < 1:
                    page_size = MAX_SEARCH_PAGE_SIZE
                if page_size > MAX_SEARCH_PAGE_SIZE:
                    logger.warning(f"Search limit {page_size} exceeds API max ({MAX_SEARCH_PAGE_SIZE}). Capping.")
                    page_size = MAX_SEARCH_PAGE_SIZE
            except ValueError:
                logger.warning(f"Invalid limit format: '{limit_str}'. Using default of {MAX_SEARCH_PAGE_SIZE}.")

        person_id, person_id_error = convert_id_string(person_id_str, "person_id")
        if person_id_error:
            logger.error(person_id_error)
            return format_tool_response(False, error_message=person_id_error)

        organization_id, org_id_error = convert_id_string(organization_id_str, "organization_id")
        if org_id_error:
            logger.error(org_id_error)
            return format_tool_response(False, error_message=org_id_error)

        fields = None
        if fields_str:
            fields = [field.strip() for field in fields_str.split(",")]

        include_fields = None
        if include_fields_str:
            include_fields = [field.strip() for field in include_fields_str.split(",")]

        if status and status not in ["open", "won", "lost"]:
            error_message = f"Invalid status: '{status}'. Must be one of: open, won, lost"
            logger.error(error_message)
            return format_tool_response(False, error_message=error_message)

        all_results = []
        current_cursor = cursor
        pages_fetched = 0

        while True:
            deals_list, next_cursor = await pd_mcp_ctx.pipedrive_client.deals.search_deals(
                term=term,
                fields=fields,
                exact_match=exact_match,
                person_id=person_id,
                organization_id=organization_id,
                status=status,
                include_fields=include_fields,
                limit=page_size,
                cursor=current_cursor
            )
            all_results.extend(deals_list)
            pages_fetched += 1

            if not auto_paginate or not next_cursor or pages_fetched >= MAX_AUTO_PAGINATE_PAGES:
                break
            current_cursor = next_cursor

        logger.info(
            f"Found {len(all_results)} deals for term '{term}' "
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
            f"PipedriveAPIError in tool 'search_deals_in_pipedrive' for term '{term}': {str(e)}"
        )
        return format_tool_response(False, error_message=str(e), data=e.response_data)
    except Exception as e:
        logger.exception(
            f"Unexpected error in tool 'search_deals_in_pipedrive' for term '{term}': {str(e)}"
        )
        return format_tool_response(
            False, error_message=f"An unexpected error occurred: {str(e)}"
        )
