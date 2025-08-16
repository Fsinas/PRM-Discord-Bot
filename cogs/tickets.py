import asyncio
import time
from rapidfuzz import fuzz
import discord
from discord.ext import commands, tasks
from config import get_config, update_runtime_config
from database import Database
from transcripts import build_transcript_files
from utils.permissions import is_admin, can_manage_ticket, escalate_role
from utils.metrics import metrics

ADMIN_ADD_CONCURRENCY = 4

STATUS_PREFIXES = {
    "solved": "[Solved]",
    "rejected": "[Rejected]",
    "in_progress": "[In Progress]",
    "open": "",
    "closed": "[Closed]"
}

IN_PROGRESS_REACTION = "🛠️"
RESOLUTION_EMOJIS = {"✅":"solved","❌":"rejected"}
DEFAULT_TIMEOUT_STATUS = "closed"

HELP_PAGES = [
"Page 1: /ticket_open, /ticket_close, /ticket_reopen",
"Page 2: /ticket_claim, /ticket_unclaim, /ticket_adduser, /ticket_removeuser",
"Page 3: /ticket_listmine, /ticket_convert, /ticket_escalate, /ticket_status",
"Page 4: /admin config_get/set, /admin blacklist_add, /health"
]

class TicketCog(commands.Cog):
    def __init__(self, bot:commands.Bot, db:Database):
        self.bot=bot
        self.db=db
        self.refresh_admins.start()
        self.stale_checker.start()
        self.archive_purge.start()

    def cog_unload(self):
        self.refresh_admins.cancel()
        self.stale_checker.cancel()
        self.archive_purge.cancel()

    async def add_admins(self, thread: discord.Thread):
        cfg = get_config()
        guild = thread.guild
        members = []
        for rid in cfg.admin_role_ids:
            role = guild.get_role(rid)
            if role:
                members.extend([m for m in role.members if not m.bot])
        unique = {m.id:m for m in members}
        sem = asyncio.Semaphore(ADMIN_ADD_CONCURRENCY)
        async def add_user(member):
            async with sem:
                try:
                    await thread.add_user(member)
                except discord.HTTPException:
                    pass
        await asyncio.gather(*[add_user(m) for m in unique.values()])

    async def remove_admins(self, thread: discord.Thread):
        cfg=get_config()
        guild=thread.guild
        for rid in cfg.admin_role_ids:
            role=guild.get_role(rid)
            if not role: continue
            for member in role.members:
                try:
                    await thread.remove_user(member)
                except discord.HTTPException:
                    pass

    def normalize_name(self, name:str, target_status:str):
        base = name
        for pref in STATUS_PREFIXES.values():
            if pref and base.startswith(pref):
                base = base[len(pref):].lstrip()
        new_pref = STATUS_PREFIXES.get(target_status,"")
        return f"{new_pref} {base}" if new_pref else base

    def is_public(self, thread:discord.Thread):
        cfg=get_config()
        return thread.parent and thread.parent.id == cfg.public_channel_id and not thread.is_private()

    async def ensure_ticket_record(self, thread:discord.Thread, creator_id:int, is_private:bool, title:str):
        row = await self.db.get_ticket_by_thread(thread.id)
        if not row:
            await self.db.create_ticket(thread.guild.id, thread.id, creator_id, is_private, title)
            metrics.incr("tickets_created")

    async def duplicate_check(self, guild:discord.Guild, title:str):
        rows = await self.db.fetchall("SELECT title FROM tickets WHERE guild_id=? ORDER BY id DESC LIMIT 25", guild.id)
        for (existing,) in rows:
            score = fuzz.token_set_ratio(title, existing)/100
            if score >= get_config().duplicate_similarity:
                return existing, score
        return None,0

    async def send_log(self, guild:discord.Guild, msg:str):
        cog = self.bot.get_cog("LoggingCog")
        if cog:
            await cog.log(guild, msg)

    # Commands
    @commands.hybrid_command(name="ticket_open", description="Open a private (support channel) or public ticket.")
    @commands.cooldown(2, 30, commands.BucketType.user)
    async def ticket_open(self, ctx: commands.Context, *, title: str):
        cfg=get_config()
        if await self.db.is_blacklisted(ctx.guild.id, ctx.author.id):
            return await ctx.reply("You are blacklisted from creating tickets.")
        if not title.strip():
            return await ctx.reply("Provide a title.")
        if len(title) > cfg.max_title_len:
            title = title[:cfg.max_title_len]
            await ctx.reply(f"Title truncated to {cfg.max_title_len} chars.")
        is_private = ctx.channel.id == cfg.support_channel_id
        if not (is_private or ctx.channel.id == cfg.public_channel_id):
            return await ctx.reply("Use in configured public or support channel.")
        dup,score = await self.duplicate_check(ctx.guild, title)
        dup_msg = f" (Possible duplicate of '{dup}' score {score:.2f})" if dup else ""
        if is_private:
            thread = await ctx.channel.create_thread(name=title, type=discord.ChannelType.private_thread, reason=f"Private ticket by {ctx.author}")
            await thread.add_user(ctx.author)
            await self.add_admins(thread)
            await thread.send(f"Hello {ctx.author.mention}, please describe your issue.{dup_msg}")
            await self.ensure_ticket_record(thread, ctx.author.id, True, title)
            await self.send_log(ctx.guild, f"Private ticket opened {thread.mention} by {ctx.author} ({ctx.author.id}).")
            await ctx.reply(f"Private ticket created: {thread.mention}{dup_msg}")
        else:
            thread = await ctx.channel.create_thread(name=title, type=discord.ChannelType.public_thread, reason=f"Public ticket by {ctx.author}")
            await self.add_admins(thread)
            await thread.send(f"Thread created by {ctx.author.mention}.{dup_msg}")
            await self.ensure_ticket_record(thread, ctx.author.id, False, title)
            await self.send_log(ctx.guild, f"Public ticket opened {thread.mention} by {ctx.author} ({ctx.author.id}).")
            await ctx.reply(f"Public ticket thread: {thread.mention}{dup_msg}")

    @commands.hybrid_command(name="ticket_close", description="Close current ticket.")
    async def ticket_close(self, ctx: commands.Context):
        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.reply("Use inside ticket thread.")
        thread:discord.Thread = ctx.channel
        record = await self.db.get_ticket_by_thread(thread.id)
        if not record:
            return await ctx.reply("Not managed.")
        creator_id = record[3]
        is_private = record[4]==1
        if not can_manage_ticket(ctx.author, thread, creator_id):
            return await ctx.reply("No permission.")
        await ctx.reply("Confirm close? Reply 'yes' in 15s.")
        def check(m:discord.Message):
            return m.author.id == ctx.author.id and m.channel == thread
        try:
            msg = await self.bot.wait_for("message", timeout=15, check=check)
            if msg.content.lower() != "yes":
                return await ctx.reply("Cancelled.")
        except asyncio.TimeoutError:
            return await ctx.reply("Timed out.")
        if is_private:
            await self.remove_admins(thread)
            creator = thread.guild.get_member(creator_id)
            if creator:
                try: await thread.remove_user(creator)
                except: pass
            await thread.edit(locked=True, archived=True)
            await self.db.close_ticket(thread.id, "closed")
            await self.send_log(thread.guild, f"Private ticket closed {thread.name} ({thread.id}) by {ctx.author}.")
            files = await build_transcript_files(thread)
            log_channel = thread.guild.get_channel(get_config().log_channel_id)
            if log_channel:
                await log_channel.send(f"Transcript for {thread.name}", files=files)
            return await ctx.reply("Private ticket closed.")
        # public
        await self.remove_admins(thread)
        await thread.edit(locked=True, archived=True)
        status_msg = await thread.send("React ✅ (solved) or ❌ (rejected) within 2m. Admin or creator reaction counts.")
        for e in RESOLUTION_EMOJIS: await status_msg.add_reaction(e)
        def rcheck(reaction:discord.Reaction, user:discord.User):
            if reaction.message.id != status_msg.id: return False
            if str(reaction.emoji) not in RESOLUTION_EMOJIS: return False
            member = thread.guild.get_member(user.id)
            return member and (user.id == creator_id or is_admin(member))
        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=120, check=rcheck)
            status_key = RESOLUTION_EMOJIS[str(reaction.emoji)]
        except asyncio.TimeoutError:
            status_key = DEFAULT_TIMEOUT_STATUS
        await thread.edit(archived=False, locked=False)
        new_name = self.normalize_name(thread.name, status_key)
        await thread.edit(name=new_name, archived=True, locked=True)
        await self.db.close_ticket(thread.id, status_key)
        await self.send_log(thread.guild, f"Public ticket {thread.name} resolved as {status_key} by {ctx.author}.")
        files = await build_transcript_files(thread)
        log_channel = thread.guild.get_channel(get_config().log_channel_id)
        if log_channel:
            await log_channel.send(f"Transcript for {thread.name}", files=files)

    @commands.hybrid_command(name="ticket_reopen", description="Reopen public ticket.")
    async def ticket_reopen(self, ctx: commands.Context, *, reason: str = "No reason provided"):
        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.reply("Use inside a public ticket thread.")
        thread=ctx.channel
        record = await self.db.get_ticket_by_thread(thread.id)
        if not record: return await ctx.reply("Not managed.")
        if record[4]==1: return await ctx.reply("Private tickets cannot be reopened.")
        creator_id = record[3]
        if not can_manage_ticket(ctx.author, thread, creator_id):
            return await ctx.reply("No permission.")
        if record[5] in ("open", "in_progress"):
            return await ctx.reply("Already open.")
        await thread.edit(archived=False, locked=False)
        new_name = self.normalize_name(thread.name, "open")
        await thread.edit(name=new_name)
        await self.add_admins(thread)
        await self.db.update_status(thread.id, "open")
        await self.send_log(thread.guild, f"Public ticket reopened {thread.mention} by {ctx.author}: {reason}")
        await ctx.reply(f"Ticket reopened. Reason: {reason}")

    @commands.hybrid_command(name="ticket_claim", description="Claim ticket (staff).")
    async def ticket_claim(self, ctx: commands.Context):
        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.reply("Use inside ticket thread.")
        if not is_admin(ctx.author):
            return await ctx.reply("Staff only.")
        record = await self.db.get_ticket_by_thread(ctx.channel.id)
        if not record: return await ctx.reply("Not managed.")
        if record[10]: # claimed_by
            claimer = ctx.guild.get_member(record[10])
            claimer_name = claimer.display_name if claimer else f"User {record[10]}"
            return await ctx.reply(f"Already claimed by {claimer_name}.")
        await self.db.set_claim(ctx.channel.id, ctx.author.id)
        await ctx.reply(f"Ticket claimed by {ctx.author.mention}.")
        await self.send_log(ctx.guild, f"Ticket {ctx.channel.mention} claimed by {ctx.author}.")

    @commands.hybrid_command(name="ticket_unclaim", description="Unclaim ticket (staff).")
    async def ticket_unclaim(self, ctx: commands.Context):
        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.reply("Use inside ticket thread.")
        if not is_admin(ctx.author):
            return await ctx.reply("Staff only.")
        record = await self.db.get_ticket_by_thread(ctx.channel.id)
        if not record: return await ctx.reply("Not managed.")
        if not record[10]:
            return await ctx.reply("Not claimed.")
        if record[10] != ctx.author.id and not ctx.author.guild_permissions.administrator:
            return await ctx.reply("Can only unclaim your own tickets (unless admin).")
        await self.db.set_claim(ctx.channel.id, None)
        await ctx.reply("Ticket unclaimed.")
        await self.send_log(ctx.guild, f"Ticket {ctx.channel.mention} unclaimed by {ctx.author}.")

    @commands.hybrid_command(name="ticket_adduser", description="Add user to private ticket (staff).")
    async def ticket_adduser(self, ctx: commands.Context, member: discord.Member):
        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.reply("Use inside ticket thread.")
        if not is_admin(ctx.author):
            return await ctx.reply("Staff only.")
        record = await self.db.get_ticket_by_thread(ctx.channel.id)
        if not record: return await ctx.reply("Not managed.")
        if record[4] != 1: return await ctx.reply("Private tickets only.")
        try:
            await ctx.channel.add_user(member)
            await ctx.reply(f"Added {member.mention} to ticket.")
            await self.send_log(ctx.guild, f"{member} added to ticket {ctx.channel.mention} by {ctx.author}.")
        except discord.HTTPException as e:
            await ctx.reply(f"Failed to add user: {e}")

    @commands.hybrid_command(name="ticket_removeuser", description="Remove user from private ticket (staff).")
    async def ticket_removeuser(self, ctx: commands.Context, member: discord.Member):
        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.reply("Use inside ticket thread.")
        if not is_admin(ctx.author):
            return await ctx.reply("Staff only.")
        record = await self.db.get_ticket_by_thread(ctx.channel.id)
        if not record: return await ctx.reply("Not managed.")
        if record[4] != 1: return await ctx.reply("Private tickets only.")
        if member.id == record[3]:
            return await ctx.reply("Cannot remove ticket creator.")
        try:
            await ctx.channel.remove_user(member)
            await ctx.reply(f"Removed {member.mention} from ticket.")
            await self.send_log(ctx.guild, f"{member} removed from ticket {ctx.channel.mention} by {ctx.author}.")
        except discord.HTTPException as e:
            await ctx.reply(f"Failed to remove user: {e}")

    @commands.hybrid_command(name="ticket_listmine", description="List your open tickets.")
    async def ticket_listmine(self, ctx: commands.Context):
        tickets = await self.db.list_open_tickets_by_user(ctx.guild.id, ctx.author.id)
        if not tickets:
            return await ctx.reply("No open tickets.")
        lines = []
        for ticket in tickets[:10]:  # limit display
            thread = ctx.guild.get_thread(ticket[2])
            thread_name = thread.name if thread else f"Thread {ticket[2]}"
            lines.append(f"• {thread_name} ({ticket[5]})")
        embed = discord.Embed(title="Your Open Tickets", description="\n".join(lines), color=0x3498db)
        await ctx.reply(embed=embed, ephemeral=True if hasattr(ctx,"interaction") else False)

    @commands.hybrid_command(name="ticket_status", description="Set ticket status (staff).")
    async def ticket_status(self, ctx: commands.Context, status: str):
        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.reply("Use inside ticket thread.")
        if not is_admin(ctx.author):
            return await ctx.reply("Staff only.")
        status = status.lower()
        if status not in STATUS_PREFIXES:
            return await ctx.reply(f"Valid statuses: {', '.join(STATUS_PREFIXES.keys())}")
        record = await self.db.get_ticket_by_thread(ctx.channel.id)
        if not record: return await ctx.reply("Not managed.")
        
        new_name = self.normalize_name(ctx.channel.name, status)
        await ctx.channel.edit(name=new_name)
        await self.db.update_status(ctx.channel.id, status)
        
        # Add reaction for in_progress
        if status == "in_progress":
            try:
                # Find the first message to add reaction to
                async for message in ctx.channel.history(limit=1, oldest_first=True):
                    await message.add_reaction(IN_PROGRESS_REACTION)
                    break
            except discord.HTTPException:
                pass
        
        await ctx.reply(f"Status set to: {status}")
        await self.send_log(ctx.guild, f"Ticket {ctx.channel.mention} status changed to {status} by {ctx.author}.")

    @commands.hybrid_command(name="ticket_convert", description="Convert public ticket to private (staff).")
    async def ticket_convert(self, ctx: commands.Context):
        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.reply("Use inside ticket thread.")
        if not is_admin(ctx.author):
            return await ctx.reply("Staff only.")
        if ctx.channel.is_private():
            return await ctx.reply("Already private.")
        record = await self.db.get_ticket_by_thread(ctx.channel.id)
        if not record: return await ctx.reply("Not managed.")
        if record[4] == 1: return await ctx.reply("Already marked as private.")
        
        # Update database
        await self.db.execute("UPDATE tickets SET is_private=1 WHERE thread_id=?", ctx.channel.id)
        
        # Remove non-essential users (keep creator and admins)
        creator = ctx.guild.get_member(record[3])
        admin_role_ids = set(get_config().admin_role_ids)
        
        for member in ctx.channel.members:
            if member.bot:
                continue
            if member.id == record[3]:  # creator
                continue
            if any(r.id in admin_role_ids for r in member.roles):  # admin
                continue
            try:
                await ctx.channel.remove_user(member)
            except discord.HTTPException:
                pass
        
        await ctx.reply("Converted to private ticket.")
        await self.send_log(ctx.guild, f"Ticket {ctx.channel.mention} converted to private by {ctx.author}.")

    @commands.hybrid_command(name="ticket_escalate", description="Ping escalation role.")
    async def ticket_escalate(self, ctx: commands.Context, *, reason: str = "No reason provided"):
        if not isinstance(ctx.channel, discord.Thread):
            return await ctx.reply("Use inside ticket thread.")
        record = await self.db.get_ticket_by_thread(ctx.channel.id)
        if not record: return await ctx.reply("Not managed.")
        
        escalation = escalate_role(ctx.guild)
        if not escalation:
            return await ctx.reply("No escalation role configured.")
        
        creator_id = record[3]
        if not can_manage_ticket(ctx.author, ctx.channel, creator_id):
            return await ctx.reply("No permission.")
        
        embed = discord.Embed(title="Ticket Escalation", color=0xe74c3c)
        embed.add_field(name="Ticket", value=ctx.channel.mention)
        embed.add_field(name="Escalated by", value=ctx.author.mention)
        embed.add_field(name="Reason", value=reason, inline=False)
        
        await ctx.send(f"{escalation.mention}", embed=embed)
        await self.send_log(ctx.guild, f"Ticket {ctx.channel.mention} escalated by {ctx.author}: {reason}")

    @commands.hybrid_command(name="help_tickets", description="Paginated ticket help.")
    async def help_tickets(self, ctx: commands.Context, page: int = 1):
        if page < 1 or page > len(HELP_PAGES):
            page = 1
        embed = discord.Embed(
            title=f"Ticket Help ({page}/{len(HELP_PAGES)})",
            description=HELP_PAGES[page-1],
            color=0x3498db
        )
        await ctx.reply(embed=embed, ephemeral=True if hasattr(ctx,"interaction") else False)

    # Background tasks
    @tasks.loop(hours=6)
    async def refresh_admins(self):
        """Periodically refresh admin access to tickets"""
        # This is a placeholder for background admin refresh logic
        pass

    @tasks.loop(hours=12)
    async def stale_checker(self):
        """Check for stale tickets and send notifications"""
        # This is a placeholder for stale ticket detection logic
        pass

    @tasks.loop(hours=24)
    async def archive_purge(self):
        """Archive and purge old closed tickets"""
        # This is a placeholder for archival logic
        pass

    @refresh_admins.before_loop
    @stale_checker.before_loop
    @archive_purge.before_loop
    async def before_background_tasks(self):
        await self.bot.wait_until_ready()

    # Event handlers
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if isinstance(message.channel, discord.Thread):
            # Update last user message timestamp
            await self.db.update_last_user_message(message.channel.id)

async def setup(bot):
    await bot.add_cog(TicketCog(bot, bot.db))