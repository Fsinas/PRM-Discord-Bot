import discord
from discord.ext import commands
from config import get_config

class LoggingCog(commands.Cog):
    def __init__(self, bot:commands.Bot):
        self.bot=bot

    async def log(self, guild:discord.Guild, message:str):
        cfg=get_config()
        channel = guild.get_channel(cfg.log_channel_id)
        if channel:
            try:
                await channel.send(message[:2000])
            except discord.HTTPException:
                pass

async def setup(bot):
    await bot.add_cog(LoggingCog(bot))