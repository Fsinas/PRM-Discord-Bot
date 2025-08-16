import discord
from config import get_config

def is_admin(member: discord.Member) -> bool:
    cfg = get_config()
    role_ids = set(cfg.admin_role_ids)
    return any(r.id in role_ids for r in member.roles) or member.guild_permissions.administrator

def can_manage_ticket(member: discord.Member, thread: discord.Thread, creator_id: int) -> bool:
    return is_admin(member) or member.id == creator_id

def escalate_role(guild: discord.Guild):
    cfg = get_config()
    if cfg.escalation_role_id:
        return guild.get_role(cfg.escalation_role_id)
    return None