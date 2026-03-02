import csv
import json
import os
from pathlib import Path
from typing import Any

from agents.utils.log_util import get_logger

TOOL_SPEC = {
    "name": "ge_product_catalog",
    "description": "查询GE医疗产品目录，按类别(MRI/CT/超声)或产品名称检索产品信息，包括型号、关键特性、技术参数和竞争优势。",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Product category (MRI, CT, Ultrasound/超声) or product name/model to search"
                }
            },
            "required": ["query"]
        }
    }
}

# Category aliases for flexible matching
_CATEGORY_ALIASES = {
    "mri": "MRI",
    "磁共振": "MRI",
    "核磁": "MRI",
    "ct": "CT",
    "ultrasound": "Ultrasound",
    "超声": "Ultrasound",
    "彩超": "Ultrasound",
    "b超": "Ultrasound",
}


def _load_catalog() -> list[dict]:
    """Load GE Healthcare product catalog from CSV file."""
    catalog_path = os.getenv(
        "GE_PRODUCT_CATALOG_PATH",
        str(Path(__file__).resolve().parent.parent / "data" / "ge_healthcare_products.csv")
    )
    rows = []
    with open(catalog_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def _search_catalog(rows: list[dict], query: str) -> list[dict]:
    """Search product catalog by category, product name, or keyword.

    Search priority:
    1. Exact category match (including aliases like 超声 -> Ultrasound)
    2. Product name or model series match (case-insensitive contains)
    3. Keyword search across description, key_features, and competitive_advantages
    """
    query_lower = query.strip().lower()

    # 1. Category match (using aliases)
    matched_category = _CATEGORY_ALIASES.get(query_lower)
    if matched_category:
        results = [r for r in rows if r.get("category", "") == matched_category]
        if results:
            return results

    # Also try direct category match
    category_results = [r for r in rows if r.get("category", "").lower() == query_lower]
    if category_results:
        return category_results

    # 2. Product name or model series match
    name_results = [
        r for r in rows
        if query_lower in r.get("product_name", "").lower()
        or query_lower in r.get("model_series", "").lower()
        or query_lower in r.get("product_id", "").lower()
    ]
    if name_results:
        return name_results

    # 3. Keyword search across description, features, and advantages
    keyword_results = [
        r for r in rows
        if query_lower in r.get("description", "").lower()
        or query_lower in r.get("key_features", "").lower()
        or query_lower in r.get("competitive_advantages", "").lower()
        or query_lower in r.get("target_department", "").lower()
    ]
    return keyword_results


async def ge_product_catalog(tool: dict, **kwargs: Any) -> dict:
    """
    Query GE Healthcare product catalog for imaging equipment details.

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

        rows = _load_catalog()
        results = _search_catalog(rows, query)

        if not results:
            categories = sorted(set(r["category"] for r in rows))
            products = [f"{r['product_id']} - {r['product_name']} ({r['category']})" for r in rows]
            return {
                "toolUseId": tool_use_id,
                "status": "success",
                "content": [{"text": (
                    f"No products found matching '{query}'.\n"
                    f"Available categories: {', '.join(categories)}\n"
                    f"Available products:\n" +
                    "\n".join(f"  - {p}" for p in products)
                )}]
            }

        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"text": json.dumps(results, ensure_ascii=False, indent=2)}]
        }

    except Exception as e:
        logger = get_logger()
        logger.error(f"Error in ge_product_catalog: {str(e)}", exc_info=True)
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"Error querying GE product catalog: {str(e)}"}]
        }
