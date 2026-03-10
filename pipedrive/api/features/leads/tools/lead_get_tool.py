from typing import Any, Dict, Optional

from mcp.server.fastmcp import Context
from pydantic import ValidationError

from log_config import logger
from pipedrive.api.features.leads.models.lead import Lead
from pipedrive.api.features.shared.conversion.id_conversion import validate_uuid_string
from pipedrive.api.features.shared.utils import format_tool_response
from pipedrive.api.pipedrive_api_error import PipedriveAPIError
from pipedrive.api.pipedrive_context import PipedriveMCPContext
from pipedrive.api.features.tool_decorator import tool


@tool("leads")
async def get_lead_from_pipedrive(
    ctx: Context,
    id_str: str,
) -> str:
    """Retrieves a specific lead by its ID from Pipedrive.
    
    This tool fetches the complete details of a lead using its unique identifier.
    It returns all available information about the lead, including associated person,
    organization, labels, and other properties.
    
    Format requirements:
        - id_str: Required UUID of the lead to retrieve, in standard UUID format
          (example: "adf21080-0e10-11eb-879b-05d71fb426ec")
    
    Example:
        get_lead_from_pipedrive(
            id_str="adf21080-0e10-11eb-879b-05d71fb426ec"
        )
    
    Args:
        ctx: Context object containing the Pipedrive client
        id_str: The UUID of the lead to retrieve
    
    Returns:
        JSON string containing success status and lead data or error message.
    """
    logger.debug(f"Tool 'get_lead_from_pipedrive' ENTERED with id_str: '{id_str}'")
    
    # Validate required field
    if not id_str or not id_str.strip():
        error_msg = "Lead ID is required and cannot be empty"
        logger.error(error_msg)
        return format_tool_response(False, error_message=error_msg)
    
    # Validate UUID format
    validated_uuid, error = validate_uuid_string(id_str, "id_str")
    if error:
        logger.error(f"Invalid id_str format: {error}")
        return format_tool_response(
            False, 
            error_message=f"Invalid id_str format: {error}. Lead ID must be a valid UUID."
        )
    
    try:
        # Use the Pipedrive client from the context
        pd_mcp_ctx: PipedriveMCPContext = ctx.request_context.lifespan_context
        client = pd_mcp_ctx.pipedrive_client
        
        try:
            lead_data = await client.lead_client.get_lead(lead_id=validated_uuid)
            
            if not lead_data:
                return format_tool_response(
                    False,
                    error_message=f"Lead with ID {id_str} not found"
                )
            
            # Create a Lead model from the response for consistent formatting
            lead_model = Lead.from_api_dict(lead_data)
            
            return format_tool_response(True, data=lead_model.model_dump())
            
        except PipedriveAPIError as e:
            return format_tool_response(
                False, 
                error_message=f"Pipedrive API error: {str(e)}"
            )
            
    except ValidationError as e:
        # Handle validation errors
        logger.error(f"Validation error retrieving lead with ID '{id_str}': {str(e)}")
        return format_tool_response(False, error_message=f"Validation error: {str(e)}")
    except PipedriveAPIError as e:
        logger.error(
            f"PipedriveAPIError in tool 'get_lead_from_pipedrive' for ID '{id_str}': {str(e)} - Response Data: {e.response_data}"
        )
        return format_tool_response(False, error_message=str(e), data=e.response_data)
    except Exception as e:
        # Handle other errors
        logger.exception(
            f"Unexpected error in tool 'get_lead_from_pipedrive' for ID '{id_str}': {str(e)}"
        )
        return format_tool_response(False, error_message=f"An unexpected error occurred: {str(e)}")