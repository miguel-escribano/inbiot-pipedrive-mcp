from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context

from log_config import logger
from pipedrive.api.features.leads.models.lead import Lead
from pipedrive.api.features.shared.conversion.id_conversion import convert_id_string
from pipedrive.api.features.shared.utils import format_tool_response, safe_split_to_list
from pipedrive.api.pipedrive_api_error import PipedriveAPIError
from pipedrive.api.pipedrive_context import PipedriveMCPContext, get_pipedrive_context
from pipedrive.api.features.tool_decorator import tool


MAX_SEARCH_PAGE_SIZE = 100
MAX_AUTO_PAGINATE_PAGES = 10


@tool("leads")
async def search_leads_in_pipedrive(
    ctx: Context,
    term: str,
    fields: Optional[str] = None,
    exact_match: Optional[bool] = False,
    person_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    include_fields: Optional[str] = None,
    limit_str: Optional[str] = "100",
    cursor: Optional[str] = None,
    auto_paginate: bool = True,
) -> str:
    """Searches for leads in Pipedrive by keyword and various criteria.
    
    This tool allows you to search for leads using text search across different fields like
    title, notes, and custom fields. You can filter the results by associated person or 
    organization, and use pagination to navigate through large result sets.
    
    Format requirements:
        - term: Required search keyword (min 2 chars, or 1 if exact_match is true)
        - fields: Optional comma-separated list of fields to search in. Values can include:
          "title", "notes", "custom_fields"
        - exact_match: When true, only exact matches will be returned (default: false)
          With exact_match enabled, term can be just 1 character
        - person_id: Filter leads by associated person ID
        - organization_id: Filter leads by associated organization ID
        - include_fields: Comma-separated list of additional fields to include in results
          Currently supported: "lead.was_seen"
        - limit_str: Maximum number of results (1-100, default: 100) 
        - cursor: Pagination cursor from previous search results
    
    Example:
        search_leads_in_pipedrive(
            term="New opportunity",
            fields="title,notes",
            exact_match=False,
            person_id="123",
            limit_str="50"
        )
    
    Args:
        ctx: Context object containing the Pipedrive client
        term: The search term to look for (min 2 chars, or 1 if exact_match)
        fields: Comma-separated list of fields to search in (title, notes, custom_fields)
        exact_match: When true, only exact matches are returned (default: false)
        person_id: Filter leads by person ID
        organization_id: Filter leads by organization ID
        include_fields: Comma-separated list of additional fields to include in results
        limit_str: Maximum number of results to return (max 100, default: 100)
        cursor: Pagination cursor for retrieving additional results
    
    Returns:
        JSON string containing success status with search results and pagination info, or error message.
    """
    logger.debug(
        f"Tool 'search_leads_in_pipedrive' ENTERED with raw args: "
        f"term='{term}', fields='{fields}', exact_match='{exact_match}', "
        f"person_id='{person_id}', organization_id='{organization_id}', "
        f"include_fields='{include_fields}', limit_str='{limit_str}', cursor='{cursor}'"
    )
    
    # Sanitize empty strings to None
    fields = None if fields == "" else fields
    person_id = None if person_id == "" else person_id
    organization_id = None if organization_id == "" else organization_id
    include_fields = None if include_fields == "" else include_fields
    limit_str = None if limit_str == "" else limit_str
    cursor = None if cursor == "" else cursor
    
    # Validate required parameters
    if not term or not term.strip():
        return format_tool_response(False, error_message="Search term is required and cannot be empty")
    
    exact_match_bool = bool(exact_match)
    
    # Validate term length based on exact_match
    if not exact_match_bool and len(term.strip()) < 2:
        return format_tool_response(
            False, 
            error_message=f"Search term must be at least 2 characters long when exact_match is false. Got: '{term}'."
        )
    
    if exact_match_bool and len(term.strip()) < 1:
        return format_tool_response(
            False, 
            error_message="Search term must be at least 1 character long when exact_match is true."
        )
    
    # Convert numeric parameters
    try:
        limit_int = int(limit_str) if limit_str else 100
        if limit_int < 1:
            return format_tool_response(
                False, 
                error_message=f"Invalid limit_str: {limit_str}. Must be a positive integer."
            )
        if limit_int > 100:
            logger.warning(f"Search limit {limit_int} exceeds Pipedrive API max (100). Capping to 100.")
            limit_int = 100
    except ValueError:
        return format_tool_response(
            False, 
            error_message=f"Invalid limit_str parameter: '{limit_str}'. Must be an integer (e.g., '100', '250')."
        )
        
    # Validate fields if provided
    if fields:
        fields_list = safe_split_to_list(fields)
        valid_fields = ["title", "notes", "custom_fields"]
        for field in fields_list:
            if field not in valid_fields:
                return format_tool_response(
                    False,
                    error_message=f"Invalid search field: '{field}'. Must be one of: {', '.join(valid_fields)}"
                )
                
    # Validate include_fields if provided
    if include_fields:
        include_fields_list = safe_split_to_list(include_fields)
        valid_include_fields = ["lead.was_seen"]
        for field in include_fields_list:
            if field not in valid_include_fields:
                return format_tool_response(
                    False,
                    error_message=f"Invalid include_field: '{field}'. Must be one of: {', '.join(valid_include_fields)}"
                )
    
    # Convert ID parameters
    person_id_int = None
    if person_id:
        person_id_int, error = convert_id_string(person_id, "person_id")
        if error:
            return format_tool_response(False, error_message=error)
    
    organization_id_int = None
    if organization_id:
        organization_id_int, error = convert_id_string(organization_id, "organization_id")
        if error:
            return format_tool_response(False, error_message=error)
    
    # Process comma-separated lists
    fields_list = safe_split_to_list(fields)
    include_fields_list = safe_split_to_list(include_fields)
    
    try:
        # Use the Pipedrive client from the context
        pd_mcp_ctx: PipedriveMCPContext = get_pipedrive_context(ctx)
        client = pd_mcp_ctx.pipedrive_client
        
        try:
            all_leads_data = []
            current_cursor = cursor
            pages_fetched = 0
            last_next_cursor = None

            while True:
                results, next_cursor = await client.lead_client.search_leads(
                    term=term,
                    fields=fields_list,
                    exact_match=exact_match_bool,
                    person_id=person_id_int,
                    organization_id=organization_id_int,
                    include_fields=include_fields_list,
                    limit=limit_int,
                    cursor=current_cursor,
                )

                for result in results:
                    try:
                        lead_data = result.get("item", {})
                        if lead_data:
                            lead_data["result_score"] = result.get("result_score")
                            try:
                                lead_model = Lead.from_api_dict(lead_data)
                                all_leads_data.append(lead_model.model_dump())
                            except Exception as e:
                                logger.warning(f"Error converting lead search result: {str(e)}")
                                all_leads_data.append(lead_data)
                    except Exception as e:
                        logger.warning(f"Error processing search result: {str(e)}")
                        all_leads_data.append(result)

                pages_fetched += 1
                last_next_cursor = next_cursor

                if not auto_paginate or not next_cursor or pages_fetched >= MAX_AUTO_PAGINATE_PAGES:
                    break
                current_cursor = next_cursor

            logger.info(
                f"Found {len(all_leads_data)} leads for term '{term}' "
                f"({pages_fetched} page(s), auto_paginate={auto_paginate})"
            )

            response_data = {
                "leads": all_leads_data,
                "pagination": {
                    "next_cursor": last_next_cursor if not auto_paginate or pages_fetched >= MAX_AUTO_PAGINATE_PAGES else None,
                    "more_items_available": last_next_cursor is not None and pages_fetched >= MAX_AUTO_PAGINATE_PAGES
                }
            }
            
            return format_tool_response(True, data=response_data)
            
        except PipedriveAPIError as e:
            return format_tool_response(
                False, 
                error_message=f"Pipedrive API error: {str(e)}"
            )
            
    except ValueError as e:
        # Handle validation errors
        logger.error(f"Validation error searching leads: {str(e)}")
        return format_tool_response(False, error_message=f"Validation error: {str(e)}")
    except PipedriveAPIError as e:
        logger.error(
            f"PipedriveAPIError in tool 'search_leads_in_pipedrive': {str(e)} - Response Data: {e.response_data}"
        )
        return format_tool_response(False, error_message=str(e), data=e.response_data)
    except Exception as e:
        # Handle other errors
        logger.exception(
            f"Unexpected error in tool 'search_leads_in_pipedrive': {str(e)}"
        )
        return format_tool_response(False, error_message=f"An unexpected error occurred: {str(e)}")