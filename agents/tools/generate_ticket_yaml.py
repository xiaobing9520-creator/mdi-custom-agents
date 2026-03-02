import json
import uuid
from datetime import datetime, timezone
from typing import Any

import yaml

from agents.utils.log_util import get_logger

TOOL_SPEC = {
    "name": "generate_ticket_yaml",
    "description": "Generate a support ticket YAML file from structured ticket data. Call this after extracting info from email and CMDB lookup.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "app_id": {
                    "type": "string",
                    "description": "Application ID from CMDB"
                },
                "app_name": {
                    "type": "string",
                    "description": "Application name"
                },
                "support_team": {
                    "type": "string",
                    "description": "Support team name from CMDB"
                },
                "team_email": {
                    "type": "string",
                    "description": "Support team email from CMDB"
                },
                "business_unit": {
                    "type": "string",
                    "description": "Business unit from CMDB"
                },
                "severity": {
                    "type": "string",
                    "enum": ["P1", "P2", "P3", "P4"],
                    "description": "Severity level"
                },
                "summary": {
                    "type": "string",
                    "description": "Brief issue summary"
                },
                "description": {
                    "type": "string",
                    "description": "Detailed issue description"
                },
                "category": {
                    "type": "string",
                    "description": "Issue category (e.g. Performance, Availability, Data, Security, Configuration, Integration, Other)"
                },
                "reporter_name": {
                    "type": "string",
                    "description": "Reporter name from email"
                },
                "reporter_email": {
                    "type": "string",
                    "description": "Reporter email from email"
                }
            },
            "required": [
                "app_id", "app_name", "support_team", "team_email",
                "severity", "summary", "description", "category"
            ]
        }
    }
}


async def generate_ticket_yaml(tool: dict, **kwargs: Any) -> dict:
    """
    Generate a support ticket YAML file from structured ticket data.

    Args:
        tool: Dictionary containing tool use information including input parameters
        **kwargs: Additional keyword arguments including request_state and agent

    Returns:
        dict: Standardized response with toolUseId, status, and content
    """
    tool_use_id = tool["toolUseId"]
    try:
        tool_input = tool["input"]
        request_state = kwargs.get("request_state", {})
        queue = request_state.get("queue")

        now = datetime.now(timezone.utc)
        ticket_id = f"TKT-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

        ticket = {
            "ticket": {
                "id": ticket_id,
                "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source": "email",
                "status": "open",
                "application": {
                    "id": tool_input["app_id"],
                    "name": tool_input["app_name"],
                    "business_unit": tool_input.get("business_unit", ""),
                },
                "issue": {
                    "summary": tool_input["summary"],
                    "description": tool_input["description"],
                    "severity": tool_input["severity"],
                    "category": tool_input["category"],
                },
                "assignment": {
                    "team": tool_input["support_team"],
                    "team_email": tool_input["team_email"],
                },
                "reporter": {
                    "name": tool_input.get("reporter_name", ""),
                    "email": tool_input.get("reporter_email", ""),
                },
            }
        }

        yaml_content = yaml.dump(
            ticket,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

        # Stream YAML to user if queue is available
        if queue:
            queue.put({
                "type": "llm_text",
                "content": f"\n```yaml\n{yaml_content}```\n",
                "message_id": str(uuid.uuid4()),
            })

        # Store in agent state for later retrieval
        state = kwargs.get("agent")
        if state:
            state = state.state
            tickets = state.get("generated_tickets") or []
            tickets.append(ticket)
            state.set("generated_tickets", tickets)

        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"text": yaml_content}],
        }

    except KeyError as e:
        logger = get_logger()
        logger.error(f"Missing required field in generate_ticket_yaml: {e}", exc_info=True)
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Error: missing required field {e}"}],
        }
    except Exception as e:
        logger = get_logger()
        logger.error(f"Error in generate_ticket_yaml: {str(e)}", exc_info=True)
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Error generating ticket YAML: {str(e)}"}],
        }
