import csv
import json
import os
from pathlib import Path
from typing import Any

from agents.utils.log_util import get_logger

TOOL_SPEC = {
    "name": "cmdb_lookup",
    "description": "Query the CMDB to find application details by app_id or app_name. Returns app_id, app_name, support_team, team_email, business_unit, criticality, and other application metadata.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Application ID (e.g. APP-001) or application name (e.g. SAP ERP) to search for"
                }
            },
            "required": ["query"]
        }
    }
}


def _load_cmdb() -> list[dict]:
    """Load CMDB data from CSV file."""
    cmdb_path = os.getenv(
        "CMDB_FILE_PATH",
        str(Path(__file__).resolve().parent.parent / "data" / "cmdb.csv")
    )
    rows = []
    with open(cmdb_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def _search_cmdb(rows: list[dict], query: str) -> list[dict]:
    """Search CMDB by exact app_id match first, then fuzzy app_name match."""
    query_upper = query.strip().upper()
    query_lower = query.strip().lower()

    # Exact app_id match
    exact = [r for r in rows if r.get("app_id", "").upper() == query_upper]
    if exact:
        return exact

    # Fuzzy app_name match (case-insensitive contains)
    fuzzy = [r for r in rows if query_lower in r.get("app_name", "").lower()]
    return fuzzy


async def cmdb_lookup(tool: dict, **kwargs: Any) -> dict:
    """
    Query the CMDB for application details.

    Args:
        tool: Dictionary containing tool use information including input parameters
        **kwargs: Additional keyword arguments including request_state

    Returns:
        dict: Standardized response with toolUseId, status, and content
    """
    tool_use_id = tool["toolUseId"]
    try:
        tool_input = tool["input"]
        query = tool_input.get("query", "").strip()

        if not query:
            return {
                "toolUseId": tool_use_id,
                "status": "error",
                "content": [{"text": "Error: query parameter is required"}]
            }

        rows = _load_cmdb()
        results = _search_cmdb(rows, query)

        if not results:
            available = [f"{r['app_id']} - {r['app_name']}" for r in rows]
            return {
                "toolUseId": tool_use_id,
                "status": "success",
                "content": [{"text": (
                    f"No application found matching '{query}'. "
                    f"Available applications:\n" +
                    "\n".join(f"  - {a}" for a in available)
                )}]
            }

        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"text": json.dumps(results, ensure_ascii=False, indent=2)}]
        }

    except Exception as e:
        logger = get_logger()
        logger.error(f"Error in cmdb_lookup: {str(e)}", exc_info=True)
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Error querying CMDB: {str(e)}"}]
        }
