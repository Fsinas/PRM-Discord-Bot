import platform, time
import discord
from discord.ext import commands
from utils.metrics import metrics
from config import get_config

START_TIME = time.time()
VERSION="1.0.0"

class Health(commands.Cog):
    def __init__(self, bot):
        self.bot=bot

    @commands.hybrid_command(name="health", description="Bot health / diagnostics.")
    async def health(self, ctx: commands.Context):
        uptime = time.time()-START_TIME
        snap = metrics.snapshot()
        embed = discord.Embed(title="Health", color=0x2ecc71)
        embed.add_field(name="Latency", value=f"{self.bot.latency*1000:.0f} ms")
        embed.add_field(name="Uptime", value=f"{uptime/3600:.2f} h")
        embed.add_field(name="Tickets Created", value=str(snap.get("tickets_created",0)))
        embed.add_field(name="Version", value=VERSION)
        embed.add_field(name="Python", value=platform.python_version())
        cfg=get_config()
        embed.add_field(name="Anonymize Public", value=str(cfg.anonymize_public))
        await ctx.reply(embed=embed, ephemeral=True if hasattr(ctx,"interaction") else False)

async def setup(bot):
    await bot.add_cog(Health(bot))