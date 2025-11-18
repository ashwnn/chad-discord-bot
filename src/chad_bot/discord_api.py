import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

class DiscordApiClient:
    def __init__(self, token: Optional[str]):
        self.token = token
        self.base_url = "https://discord.com/api/v10"

    async def get_guild(self, guild_id: str) -> Optional[Dict[str, Any]]:
        """Fetch guild information from Discord API."""
        if not self.token:
            logger.warning("Discord token missing, skipping guild fetch")
            return None
        
        async with httpx.AsyncClient(base_url=self.base_url, timeout=15.0) as client:
            try:
                resp = await client.get(
                    f"/guilds/{guild_id}",
                    headers={"Authorization": f"Bot {self.token}"},
                )
                if resp.status_code >= 400:
                    logger.error("Failed fetching guild %s: %s - %s", guild_id, resp.status_code, resp.text)
                    return None
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:  # noqa: BLE001
                logger.error("Error fetching guild %s: %s", guild_id, exc)
                return None

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
                    "image": {
                        "url": embed_url
                    },
                    "color": 2563755  # Discord blue hex #2563eb
                }
            ]
            # Don't duplicate content in embed if already in message
            if not mention_user_id:
                payload["embeds"][0]["description"] = content
        
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
