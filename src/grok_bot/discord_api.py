import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class DiscordApiClient:
    def __init__(self, token: Optional[str]):
        self.token = token
        self.base_url = "https://discord.com/api/v10"

    async def send_message(
        self,
        *,
        channel_id: str,
        content: str,
        embed_url: Optional[str] = None,
        mention_user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self.token:
            logger.warning("Discord token missing, skipping send")
            return None
        
        payload: Dict[str, Any] = {}
        
        # Build the message content with optional mention
        if mention_user_id:
            payload["content"] = f"<@{mention_user_id}> {content}"
        else:
            payload["content"] = content
        
        # Add embed if image URL provided
        if embed_url:
            payload["embeds"] = [
                {
                    "title": "Grok Image",
                    "description": content if content != "Here's your approved image." else "Generated image from Grok",
                    "image": {
                        "url": embed_url
                    },
                    "color": 2563755  # Discord blue hex #2563eb
                }
            ]
        
        async with httpx.AsyncClient(base_url=self.base_url, timeout=15.0) as client:
            resp = await client.post(
                f"/channels/{channel_id}/messages",
                headers={"Authorization": f"Bot {self.token}"},
                json=payload,
            )
            if resp.status_code >= 400:
                logger.error("Failed sending message to Discord: %s - %s", resp.status_code, resp.text)
            resp.raise_for_status()
            return resp.json()
