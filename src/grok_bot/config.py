import os
from dataclasses import dataclass
from typing import Optional


DEFAULT_SYSTEM_PROMPT = (
    "You are GrokBot for Discord. Always answer the user's question directly and concisely. "
    "Lead with the helpful answer, then optionally add one short sarcastic or blunt comment. "
    "Tone can be mildly rude but never hateful. Avoid slurs, protected class insults, explicit "
    "sexual content, or graphic violence. If the user prompt is unclear, spammy, or misuses "
    "commands, call it out and tell them briefly what to do instead."
)


@dataclass
class Settings:
    """Runtime configuration pulled from environment variables."""

    discord_token: Optional[str] = os.getenv("DISCORD_BOT_TOKEN")
    grok_api_key: Optional[str] = os.getenv("GROK_API_KEY")
    grok_api_base: str = os.getenv("GROK_API_BASE", "https://api.x.ai/v1")
    grok_chat_model: str = os.getenv("GROK_CHAT_MODEL", "grok-beta")
    grok_image_model: str = os.getenv("GROK_IMAGE_MODEL", "grok-image-1")
    database_path: str = os.getenv("DATABASE_PATH", "grok_bot.sqlite3")
    web_host: str = os.getenv("WEB_HOST", "0.0.0.0")
    web_port: int = int(os.getenv("WEB_PORT", "8000"))
    max_prompt_chars: int = int(os.getenv("MAX_PROMPT_CHARS", "4000"))

    @property
    def has_grok(self) -> bool:
        return bool(self.grok_api_key)

    @property
    def has_discord(self) -> bool:
        return bool(self.discord_token)
