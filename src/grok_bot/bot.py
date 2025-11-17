import asyncio
import logging
from typing import Optional

import discord
from discord.ext import commands

from .config import Settings
from .database import Database
from .grok_client import GrokClient
from .service import RequestProcessor

logger = logging.getLogger(__name__)


class GrokDiscordBot(commands.Bot):
    def __init__(self, settings: Settings, db: Database, processor: RequestProcessor):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.settings = settings
        self.db = db
        self.processor = processor

    async def setup_hook(self) -> None:
        await self.db.connect()
        await self.db.create_schema()
        logger.info("Database ready at %s", self.db.path)

    async def on_ready(self):
        logger.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "unknown")
        await self.change_presence(activity=discord.Game(name="!ask / !image"))


def _guild_id(ctx: commands.Context) -> Optional[str]:
    return str(ctx.guild.id) if ctx.guild else None


def _channel_id(ctx: commands.Context) -> str:
    return str(ctx.channel.id)


def _user_id(ctx: commands.Context) -> str:
    return str(ctx.author.id)


def _is_admin_user(ctx: commands.Context) -> bool:
    perms = ctx.author.guild_permissions if hasattr(ctx.author, "guild_permissions") else None
    return bool(perms and (perms.administrator or perms.manage_guild))


def _admin_label(ctx: commands.Context) -> str:
    return " (admin)" if _is_admin_user(ctx) else ""


async def _determine_admin(db: Database, ctx: commands.Context) -> bool:
    guild_id = _guild_id(ctx)
    if not guild_id:
        return False
    db_admin = await db.is_admin(_user_id(ctx), guild_id)
    return db_admin or _is_admin_user(ctx)


def create_bot(settings: Settings) -> GrokDiscordBot:
    db = Database(settings.database_path)
    grok = GrokClient(
        api_key=settings.grok_api_key,
        api_base=settings.grok_api_base,
        chat_model=settings.grok_chat_model,
        image_model=settings.grok_image_model,
    )
    processor = RequestProcessor(db=db, grok=grok, settings=settings)
    bot = GrokDiscordBot(settings=settings, db=db, processor=processor)

    @bot.command(name="ask", help="Ask Grok a question")
    async def ask_command(ctx: commands.Context, *, question: str = ""):
        guild_id = _guild_id(ctx)
        if not guild_id:
            await ctx.send("This only works in servers, not DMs.")
            return
        is_admin = await _determine_admin(bot.db, ctx)
        result = await bot.processor.process_chat(
            guild_id=guild_id,
            channel_id=_channel_id(ctx),
            user_id=_user_id(ctx),
            discord_message_id=str(ctx.message.id),
            content=question or "",
            is_admin=is_admin,
        )
        await ctx.send(result.reply)
        logger.info("Handled !ask %s%s", _user_id(ctx), _admin_label(ctx))

    @bot.command(name="image", help="Generate an image with Grok")
    async def image_command(ctx: commands.Context, *, prompt: str = ""):
        guild_id = _guild_id(ctx)
        if not guild_id:
            await ctx.send("This only works in servers, not DMs.")
            return
        is_admin = await _determine_admin(bot.db, ctx)
        result = await bot.processor.process_image(
            guild_id=guild_id,
            channel_id=_channel_id(ctx),
            user_id=_user_id(ctx),
            discord_message_id=str(ctx.message.id),
            prompt=prompt or "",
            is_admin=is_admin,
        )
        if result.image_url:
            embed = discord.Embed(title="Grok image")
            embed.set_image(url=result.image_url)
            await ctx.send(result.reply, embed=embed)
        else:
            await ctx.send(result.reply)
        logger.info("Handled !image %s%s", _user_id(ctx), _admin_label(ctx))

    return bot


async def run_bot():
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    bot = create_bot(settings)
    if not settings.discord_token:
        logger.error("DISCORD_BOT_TOKEN is required to start the bot.")
        return
    async with bot:
        await bot.start(settings.discord_token)


if __name__ == "__main__":
    asyncio.run(run_bot())
