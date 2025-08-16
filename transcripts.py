import discord
import html
import io
from datetime import timezone

async def export_plain(thread: discord.Thread) -> bytes:
    lines = []
    async for message in thread.history(limit=None, oldest_first=True):
        ts = message.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        author = f"{message.author} ({message.author.id})"
        content = message.content.replace("\n"," \\n ")
        lines.append(f"[{ts} UTC] {author}: {content}")
    return "\n".join(lines).encode("utf-8")

async def export_html(thread: discord.Thread) -> bytes:
    buf = ["<html><head><meta charset='utf-8'><title>Transcript</title></head><body>"]
    buf.append(f"<h1>Transcript: {html.escape(thread.name)}</h1>")
    async for message in thread.history(limit=None, oldest_first=True):
        ts = message.created_at.astimezone(timezone.utc).isoformat()
        buf.append("<div class='msg'>")
        buf.append(f"<span class='ts'>{ts}</span> ")
        buf.append(f"<strong>{html.escape(str(message.author))}</strong>: ")
        buf.append(f"<span class='content'>{html.escape(message.content)}</span>")
        buf.append("</div>")
    buf.append("</body></html>")
    return "\n".join(buf).encode("utf-8")

async def build_transcript_files(thread: discord.Thread):
    plain = await export_plain(thread)
    html_bytes = await export_html(thread)
    return [
        discord.File(io.BytesIO(plain), filename=f"transcript-{thread.id}.txt"),
        discord.File(io.BytesIO(html_bytes), filename=f"transcript-{thread.id}.html"),
    ]