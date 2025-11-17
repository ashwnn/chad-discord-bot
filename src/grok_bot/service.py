from dataclasses import dataclass
from typing import Optional

from .config import Settings
from .database import Database
from .grok_client import GrokClient
from .rate_limits import RateLimitResult, RateLimitRule, check_rate_limit
from .spam import ValidationResult, validate_prompt


@dataclass
class ProcessResult:
    reply: str
    log_id: Optional[int]
    image_url: Optional[str] = None
    status: str = "auto_responded"
    error: Optional[str] = None


class RequestProcessor:
    def __init__(self, db: Database, grok: GrokClient, settings: Settings):
        self.db = db
        self.grok = grok
        self.settings = settings
        self.price_per_m_token = 5.0

    async def _check_duplicate(self, guild_id: str, user_id: str, content: str, window_seconds: int) -> bool:
        async with self.db.conn.execute(
            """
            SELECT 1 FROM message_log
            WHERE guild_id=? AND user_id=? AND user_content=? AND created_at >= datetime('now', ?)
            LIMIT 1;
            """,
            (guild_id, user_id, content, f"-{window_seconds} seconds"),
        ) as cur:
            return bool(await cur.fetchone())

    async def _check_budgets_chat(self, guild_id: str, user_id: str, config) -> Optional[str]:
        usage = await self.db.get_usage(guild_id, user_id)
        if usage["user"]["chat_tokens_used"] >= config.user_daily_chat_token_limit:
            return "Your daily chat budget is toast. Ask again tomorrow."
        if usage["guild"]["chat_tokens_used"] >= config.global_daily_chat_token_limit:
            return "This guild used up the chat budget for today. Cool your jets."
        return None

    async def _check_budgets_image(self, guild_id: str, user_id: str, config) -> Optional[str]:
        usage = await self.db.get_usage(guild_id, user_id)
        if usage["user"]["images_generated"] >= config.user_daily_image_limit:
            return "You hit the image quota for today."
        if usage["guild"]["images_generated"] >= config.global_daily_image_limit:
            return "Your server burned through the image budget today."
        return None

    async def process_chat(
        self,
        *,
        guild_id: str,
        channel_id: str,
        user_id: str,
        discord_message_id: Optional[str],
        content: str,
        is_admin: bool,
    ) -> ProcessResult:
        config = await self.db.get_guild_config(guild_id)
        validation: ValidationResult = validate_prompt(content, max_chars=config.max_prompt_chars)
        if not validation.ok:
            log_id = await self.db.record_message(
                guild_id=guild_id,
                channel_id=channel_id,
                user_id=user_id,
                discord_message_id=discord_message_id,
                command_type="ask",
                user_content=content,
                status="auto_responded",
                error_code=validation.reason,
                error_detail=validation.reply,
            )
            return ProcessResult(reply=validation.reply or "Invalid input.", log_id=log_id, status="auto_responded")

        duplicate = await self._check_duplicate(guild_id, user_id, content, config.duplicate_window_seconds)
        if duplicate:
            reply = "You literally just asked that. Wait a bit."
            log_id = await self.db.record_message(
                guild_id=guild_id,
                channel_id=channel_id,
                user_id=user_id,
                discord_message_id=discord_message_id,
                command_type="ask",
                user_content=content,
                status="auto_responded",
                error_code="duplicate",
                error_detail=reply,
            )
            return ProcessResult(reply=reply, log_id=log_id, status="auto_responded")

        rate_limit_rule = RateLimitRule(config.ask_window_seconds, config.ask_max_per_window)
        rate_result: RateLimitResult = await check_rate_limit(
            self.db,
            guild_id=guild_id,
            user_id=user_id,
            command_type="ask",
            rule=rate_limit_rule,
        )
        if not rate_result.allowed:
            log_id = await self.db.record_message(
                guild_id=guild_id,
                channel_id=channel_id,
                user_id=user_id,
                discord_message_id=discord_message_id,
                command_type="ask",
                user_content=content,
                status="auto_responded",
                error_code="rate_limited",
                error_detail=rate_result.reply,
            )
            return ProcessResult(reply=rate_result.reply or "Rate limit hit.", log_id=log_id)

        budget_error = await self._check_budgets_chat(guild_id, user_id, config)
        if budget_error:
            log_id = await self.db.record_message(
                guild_id=guild_id,
                channel_id=channel_id,
                user_id=user_id,
                discord_message_id=discord_message_id,
                command_type="ask",
                user_content=content,
                status="auto_responded",
                error_code="chat_budget",
                error_detail=budget_error,
            )
            return ProcessResult(reply=budget_error, log_id=log_id)

        if config.auto_approve_enabled and not (config.admin_bypass_auto_approve and is_admin):
            log_id = await self.db.record_message(
                guild_id=guild_id,
                channel_id=channel_id,
                user_id=user_id,
                discord_message_id=discord_message_id,
                command_type="ask",
                user_content=content,
                status="pending_approval",
                needs_approval=True,
            )
            return ProcessResult(reply="Your request is waiting for an admin to approve.", log_id=log_id, status="pending_approval")

        try:
            grok_result = await self.grok.chat(
                system_prompt=config.system_prompt,
                user_content=content,
                temperature=config.temperature,
                max_tokens=config.max_completion_tokens,
            )
        except Exception as exc:  # noqa: BLE001
            log_id = await self.db.record_message(
                guild_id=guild_id,
                channel_id=channel_id,
                user_id=user_id,
                discord_message_id=discord_message_id,
                command_type="ask",
                user_content=content,
                status="error",
                error_code="grok_error",
                error_detail=str(exc),
            )
            return ProcessResult(reply="Grok had a meltdown. Try again later.", log_id=log_id, status="error", error=str(exc))

        usage = grok_result.usage or {}
        total_tokens = usage.get("total_tokens", 0) or 0
        cost = (total_tokens / 1_000_000) * self.price_per_m_token if total_tokens else None
        log_id = await self.db.record_message(
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            discord_message_id=discord_message_id,
            command_type="ask",
            user_content=content,
            grok_request_payload={"model": self.grok.chat_model, "max_tokens": config.max_completion_tokens},
            grok_response_content=grok_result.content,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=total_tokens,
            estimated_cost_usd=cost,
            status="auto_responded",
        )
        if total_tokens:
            await self.db.increment_daily_chat_usage(guild_id, user_id, total_tokens)
        return ProcessResult(reply=grok_result.content, log_id=log_id, status="auto_responded")

    async def process_image(
        self,
        *,
        guild_id: str,
        channel_id: str,
        user_id: str,
        discord_message_id: Optional[str],
        prompt: str,
        is_admin: bool,
    ) -> ProcessResult:
        config = await self.db.get_guild_config(guild_id)
        validation = validate_prompt(prompt, max_chars=config.max_prompt_chars)
        if not validation.ok:
            log_id = await self.db.record_message(
                guild_id=guild_id,
                channel_id=channel_id,
                user_id=user_id,
                discord_message_id=discord_message_id,
                command_type="image",
                user_content=prompt,
                status="auto_responded",
                error_code=validation.reason,
                error_detail=validation.reply,
            )
            return ProcessResult(reply=validation.reply or "Invalid input.", log_id=log_id)

        duplicate = await self._check_duplicate(guild_id, user_id, prompt, config.duplicate_window_seconds)
        if duplicate:
            reply = "You already asked for that image. Chill."
            log_id = await self.db.record_message(
                guild_id=guild_id,
                channel_id=channel_id,
                user_id=user_id,
                discord_message_id=discord_message_id,
                command_type="image",
                user_content=prompt,
                status="auto_responded",
                error_code="duplicate",
                error_detail=reply,
            )
            return ProcessResult(reply=reply, log_id=log_id)

        rate_result = await check_rate_limit(
            self.db,
            guild_id=guild_id,
            user_id=user_id,
            command_type="image",
            rule=RateLimitRule(config.image_window_seconds, config.image_max_per_window),
        )
        if not rate_result.allowed:
            log_id = await self.db.record_message(
                guild_id=guild_id,
                channel_id=channel_id,
                user_id=user_id,
                discord_message_id=discord_message_id,
                command_type="image",
                user_content=prompt,
                status="auto_responded",
                error_code="rate_limited",
                error_detail=rate_result.reply,
            )
            return ProcessResult(reply=rate_result.reply or "Too many image requests.", log_id=log_id)

        budget_error = await self._check_budgets_image(guild_id, user_id, config)
        if budget_error:
            log_id = await self.db.record_message(
                guild_id=guild_id,
                channel_id=channel_id,
                user_id=user_id,
                discord_message_id=discord_message_id,
                command_type="image",
                user_content=prompt,
                status="auto_responded",
                error_code="image_budget",
                error_detail=budget_error,
            )
            return ProcessResult(reply=budget_error, log_id=log_id)

        if config.auto_approve_enabled and not (config.admin_bypass_auto_approve and is_admin):
            log_id = await self.db.record_message(
                guild_id=guild_id,
                channel_id=channel_id,
                user_id=user_id,
                discord_message_id=discord_message_id,
                command_type="image",
                user_content=prompt,
                status="pending_approval",
                needs_approval=True,
            )
            return ProcessResult(reply="Image request queued for admin approval.", log_id=log_id, status="pending_approval")

        try:
            image_result = await self.grok.generate_image(prompt=prompt)
        except Exception as exc:  # noqa: BLE001
            log_id = await self.db.record_message(
                guild_id=guild_id,
                channel_id=channel_id,
                user_id=user_id,
                discord_message_id=discord_message_id,
                command_type="image",
                user_content=prompt,
                status="error",
                error_code="grok_error",
                error_detail=str(exc),
            )
            return ProcessResult(reply="Image service failed. Try later.", log_id=log_id, status="error", error=str(exc))

        image_url = image_result.urls[0] if image_result.urls else None
        log_id = await self.db.record_message(
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            discord_message_id=discord_message_id,
            command_type="image",
            user_content=prompt,
            grok_request_payload={"model": self.grok.image_model},
            grok_image_urls=image_result.urls,
            status="auto_responded",
        )
        await self.db.increment_daily_image_usage(guild_id, user_id, 1)
        reply = image_url or "Image generated, but no URL returned."
        return ProcessResult(reply=reply, log_id=log_id, image_url=image_url, status="auto_responded")
