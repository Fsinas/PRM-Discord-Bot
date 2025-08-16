import discord
from discord.ext import commands
from config import get_config, update_runtime_config
from utils.permissions import is_admin

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Only allow admins to use admin commands"""
        return is_admin(ctx.author)

    @commands.hybrid_group(name="admin", description="Administrative commands.")
    async def admin(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.reply("Use a subcommand: config_get, config_set, blacklist_add, perms_check")

    @admin.command(name="config_get", description="Get runtime configuration values.")
    async def config_get(self, ctx: commands.Context, key: str = None):
        cfg = get_config()
        runtime_config = cfg.to_dict()
        
        if key:
            if key in runtime_config:
                value = runtime_config[key]
                await ctx.reply(f"`{key}`: `{value}`", ephemeral=True)
            else:
                await ctx.reply(f"Unknown config key: `{key}`\nAvailable: {', '.join(runtime_config.keys())}", ephemeral=True)
        else:
            lines = [f"`{k}`: `{v}`" for k, v in runtime_config.items()]
            embed = discord.Embed(title="Runtime Configuration", description="\n".join(lines), color=0x3498db)
            await ctx.reply(embed=embed, ephemeral=True)

    @admin.command(name="config_set", description="Set runtime configuration values.")
    async def config_set(self, ctx: commands.Context, key: str, value: str):
        cfg = get_config()
        runtime_config = cfg.to_dict()
        
        if key not in runtime_config:
            available = ', '.join(runtime_config.keys())
            return await ctx.reply(f"Unknown config key: `{key}`\nAvailable: {available}")
        
        # Type conversion based on current value type
        current_value = getattr(cfg, key)
        try:
            if isinstance(current_value, bool):
                new_value = value.lower() in ('true', '1', 'yes', 'on')
            elif isinstance(current_value, int):
                new_value = int(value)
            elif isinstance(current_value, float):
                new_value = float(value)
            else:
                new_value = value
        except ValueError:
            return await ctx.reply(f"Invalid value type for `{key}`. Expected {type(current_value).__name__}.")
        
        # Update config
        update_runtime_config(**{key: new_value})
        await ctx.reply(f"Updated `{key}` to `{new_value}`")
        
        # Log the change
        cog = self.bot.get_cog("LoggingCog")
        if cog:
            await cog.log(ctx.guild, f"Config updated by {ctx.author}: {key} = {new_value}")

    @admin.command(name="blacklist_add", description="Blacklist a user from creating tickets.")
    async def blacklist_add(self, ctx: commands.Context, user: discord.User, *, reason: str = "No reason provided"):
        await self.bot.db.add_blacklist(ctx.guild.id, user.id, reason)
        await ctx.reply(f"Blacklisted {user.mention} from creating tickets.\nReason: {reason}")
        
        # Log the action
        cog = self.bot.get_cog("LoggingCog")
        if cog:
            await cog.log(ctx.guild, f"User blacklisted by {ctx.author}: {user} ({user.id}) - {reason}")

    @admin.command(name="blacklist_remove", description="Remove user from blacklist.")
    async def blacklist_remove(self, ctx: commands.Context, user: discord.User):
        await self.bot.db.execute("DELETE FROM blacklist WHERE guild_id=? AND user_id=?", ctx.guild.id, user.id)
        await ctx.reply(f"Removed {user.mention} from blacklist.")
        
        # Log the action
        cog = self.bot.get_cog("LoggingCog")
        if cog:
            await cog.log(ctx.guild, f"User removed from blacklist by {ctx.author}: {user} ({user.id})")

    @admin.command(name="blacklist_list", description="List blacklisted users.")
    async def blacklist_list(self, ctx: commands.Context):
        rows = await self.bot.db.fetchall("SELECT user_id, reason FROM blacklist WHERE guild_id=?", ctx.guild.id)
        if not rows:
            return await ctx.reply("No users blacklisted.", ephemeral=True)
        
        lines = []
        for user_id, reason in rows[:20]:  # Limit to 20 entries
            user = self.bot.get_user(user_id)
            user_name = f"{user} ({user_id})" if user else f"User {user_id}"
            lines.append(f"• {user_name}: {reason}")
        
        embed = discord.Embed(title="Blacklisted Users", description="\n".join(lines), color=0xe74c3c)
        await ctx.reply(embed=embed, ephemeral=True)

    @admin.command(name="perms_check", description="Check bot permissions and configuration.")
    async def perms_check(self, ctx: commands.Context):
        cfg = get_config()
        guild = ctx.guild
        
        # Check channel permissions
        checks = []
        
        # Public channel
        public_channel = guild.get_channel(cfg.public_channel_id)
        if public_channel:
            perms = public_channel.permissions_for(guild.me)
            checks.append(f"📍 Public Channel: {public_channel.mention}")
            checks.append(f"   • Send Messages: {'✅' if perms.send_messages else '❌'}")
            checks.append(f"   • Create Threads: {'✅' if perms.create_public_threads else '❌'}")
            checks.append(f"   • Manage Threads: {'✅' if perms.manage_threads else '❌'}")
        else:
            checks.append(f"❌ Public Channel: Not found (ID: {cfg.public_channel_id})")
        
        # Support channel
        support_channel = guild.get_channel(cfg.support_channel_id)
        if support_channel:
            perms = support_channel.permissions_for(guild.me)
            checks.append(f"🔒 Support Channel: {support_channel.mention}")
            checks.append(f"   • Send Messages: {'✅' if perms.send_messages else '❌'}")
            checks.append(f"   • Create Private Threads: {'✅' if perms.create_private_threads else '❌'}")
            checks.append(f"   • Manage Threads: {'✅' if perms.manage_threads else '❌'}")
        else:
            checks.append(f"❌ Support Channel: Not found (ID: {cfg.support_channel_id})")
        
        # Log channel
        log_channel = guild.get_channel(cfg.log_channel_id)
        if log_channel:
            perms = log_channel.permissions_for(guild.me)
            checks.append(f"📋 Log Channel: {log_channel.mention}")
            checks.append(f"   • Send Messages: {'✅' if perms.send_messages else '❌'}")
            checks.append(f"   • Attach Files: {'✅' if perms.attach_files else '❌'}")
        else:
            checks.append(f"❌ Log Channel: Not found (ID: {cfg.log_channel_id})")
        
        # Admin roles
        checks.append(f"👥 Admin Roles:")
        for role_id in cfg.admin_role_ids:
            role = guild.get_role(role_id)
            if role:
                checks.append(f"   • {role.name}: ✅ ({len(role.members)} members)")
            else:
                checks.append(f"   • Role ID {role_id}: ❌ Not found")
        
        # Escalation role
        if cfg.escalation_role_id:
            esc_role = guild.get_role(cfg.escalation_role_id)
            if esc_role:
                checks.append(f"🆙 Escalation Role: {esc_role.name} ✅")
            else:
                checks.append(f"❌ Escalation Role: Not found (ID: {cfg.escalation_role_id})")
        else:
            checks.append(f"🆙 Escalation Role: Not configured")
        
        # Database
        try:
            await self.bot.db.fetchone("SELECT 1")
            checks.append(f"💾 Database: ✅ Connected")
        except Exception as e:
            checks.append(f"❌ Database: Error - {e}")
        
        embed = discord.Embed(
            title="Bot Permissions & Configuration Check", 
            description="\n".join(checks), 
            color=0x2ecc71
        )
        await ctx.reply(embed=embed, ephemeral=True)

    @admin.command(name="stats", description="Show ticket statistics.")
    async def stats(self, ctx: commands.Context):
        # Overall stats
        total_tickets = await self.bot.db.fetchone("SELECT COUNT(*) FROM tickets WHERE guild_id=?", ctx.guild.id)
        total_count = total_tickets[0] if total_tickets else 0
        
        # Status breakdown
        status_counts = await self.bot.db.count_by_status(ctx.guild.id)
        status_dict = {status: count for status, count in status_counts}
        
        # Recent tickets (last 7 days)
        import time
        week_ago = int(time.time()) - (7 * 24 * 60 * 60)
        recent = await self.bot.db.fetchone("SELECT COUNT(*) FROM tickets WHERE guild_id=? AND created_at > ?", 
                                           ctx.guild.id, week_ago)
        recent_count = recent[0] if recent else 0
        
        embed = discord.Embed(title="Ticket Statistics", color=0x3498db)
        embed.add_field(name="Total Tickets", value=str(total_count), inline=True)
        embed.add_field(name="Last 7 Days", value=str(recent_count), inline=True)
        embed.add_field(name="‎", value="‎", inline=True)  # spacer
        
        # Status breakdown
        status_lines = []
        for status in ["open", "in_progress", "solved", "rejected", "closed"]:
            count = status_dict.get(status, 0)
            status_lines.append(f"{status.title()}: {count}")
        
        embed.add_field(name="Status Breakdown", value="\n".join(status_lines), inline=False)
        
        await ctx.reply(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))