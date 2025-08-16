import discord
from discord.ext import commands
import asyncio
import signal
from config import get_config
from database import Database
from utils.logging_ext import setup_logging

INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.guilds = True
INTENTS.members = True
INTENTS.reactions = True

class TicketBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS)
        self.db: Database | None = None

    async def setup_hook(self):
        await self.load_extension("cogs.logging_cog")
        await self.load_extension("cogs.health")
        await self.load_extension("cogs.tickets")
        await self.load_extension("cogs.admin")
        await self.tree.sync()

    async def on_ready(self):
        print(f"Logged in as {self.user} ({self.user.id})")

    async def close(self):
        await super().close()

bot = TicketBot()

@bot.event
async def on_command_error(ctx, error):
    from discord.ext import commands as c
    if isinstance(error, c.CommandOnCooldown):
        await ctx.reply(f"Cooldown: try again in {error.retry_after:.1f}s.")
    else:
        await ctx.reply("Error occurred.")
        raise error

async def main():
    setup_logging()
    cfg = get_config()
    if not cfg.bot_token:
        print("Set BOT_TOKEN in .env")
        return
    bot.db = Database(cfg.db_path)
    await bot.db.init()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(bot.close()))
        except NotImplementedError:
            pass
    await bot.start(cfg.bot_token)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass