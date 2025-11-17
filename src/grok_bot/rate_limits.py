from dataclasses import dataclass
from typing import Optional

from .database import Database


@dataclass
class RateLimitRule:
    window_seconds: int
    max_calls: int


@dataclass
class RateLimitResult:
    allowed: bool
    reply: Optional[str] = None


async def check_rate_limit(
    db: Database,
    *,
    guild_id: str,
    user_id: str,
    command_type: str,
    rule: RateLimitRule,
) -> RateLimitResult:
    recent = await db.count_recent(
        guild_id=guild_id, user_id=user_id, command_type=command_type, window_seconds=rule.window_seconds
    )
    if recent >= rule.max_calls:
        return RateLimitResult(
            allowed=False,
            reply="Cool it. You hit the spam limit. Try again later.",
        )
    return RateLimitResult(allowed=True)
