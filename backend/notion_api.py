import httpx
import logging
import re

logger = logging.getLogger(__name__)

NOTION_VERSION = "2022-06-28"

def extract_id_from_url(url: str) -> str:
    """
    Extracts the 32-character Notion page ID from a URL.
    Example: https://www.notion.so/workspace/Page-Name-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
    """
    # Remove hyphens if any (Notion sometimes uses them in IDs)
    match = re.search(r"([a-f0-9]{32})", url.replace("-", ""))
    if match:
        return match.group(1)
    return ""

async def create_kb_page(token: str, parent_id: str) -> dict:
    """
    Creates a new 'Jobert KB' page under the specified parent page.
    """
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    
    payload = {
        "parent": {"page_id": parent_id},
        "properties": {
            "title": [
                {
                    "text": {
                        "content": "Jobert Knowledge Base"
                    }
                }
            ]
        },
        "children": [
            {
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"type": "text", "text": {"content": "About Me"}}]
                }
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": "Use this page to provide extra context that isn't in your CV. The AI will use this to tailor your applications."}}]
                }
            },
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "Preferences"}}]
                }
            },
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": "Preferred Stack: (e.g., Python, React, Go)"}}]
                }
            },
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": "Industries: (e.g., Fintech, AI, Green Energy)"}}]
                }
            },
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "Logistics"}}]
                }
            },
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": "Relocation stance: (e.g., Open to London/NYC, Remote only)"}}]
                }
            },
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": "Notice period: (e.g., Immediate, 1 month)"}}]
                }
            }
        ]
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            logger.error(f"Notion API error: {response.text}")
            response.raise_for_status()
        return response.json()
