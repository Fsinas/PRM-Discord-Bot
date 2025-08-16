# PRM Discord Bot

Advanced Discord ticket bot providing both public and private ticket workflows.

## Key Features
- Public ticket threads in a designated channel (auto-add staff, resolution reactions, reopen support).
- Private support tickets via command, non-reopenable, transcript export on closure.
- Slash (Application) + legacy prefix commands (hybrid).
- Multi-role admin/staff support + escalation role ping.
- Status lifecycle: open, in_progress, solved, rejected, closed (auto name prefixes).
- Transcripts (TXT + HTML) stored via on-demand export at closure (posted to log channel).
- Duplicate title similarity detection (RapidFuzz) for user feedback.
- Rate limiting, configurable cooldowns.
- Runtime mutable config (subset) via `/admin config_set`.
- Claim / unclaim tickets, convert public -> private, add/remove users from private tickets.
- Blacklist users from ticket creation.
- Health / diagnostics & permission self-check commands.
- Background tasks scaffolding for stale detection & purge of old closed tickets.

## Getting Started
1. Clone repo.
2. Create virtual environment & install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in IDs (enable Developer Mode in Discord to copy IDs):
   - BOT_TOKEN
   - PUBLIC_CHANNEL_ID (channel where users can open public discussion tickets)
   - SUPPORT_CHANNEL_ID (channel where `/ticket_open` run to create private threads)
   - LOG_CHANNEL_ID (channel to receive transcripts & audit messages)
   - ADMIN_ROLE_IDS (comma-separated staff role IDs)
   - ESCALATION_ROLE_ID (optional higher tier)
4. Enable Privileged Gateway Intents (Server Members, Message Content) for the bot in the Developer Portal.
5. Run the bot:
   ```bash
   python bot.py
   ```

## Core Commands (Slash Variants Preferred)
| Command | Purpose |
|---------|---------|
| /ticket_open <title> | Create ticket (private if in support channel, else public thread) |
| /ticket_close | Close current ticket thread |
| /ticket_reopen | Reopen a closed public ticket |
| /ticket_claim /ticket_unclaim | Staff claim management |
| /ticket_adduser /ticket_removeuser | Manage participants in private tickets |
| /ticket_listmine | List your open tickets |
| /ticket_status in_progress| Set status (staff) |
| /ticket_convert | Convert public ticket to private |
| /ticket_escalate | Ping escalation role |
| /help_tickets | Paginated help |
| /admin config_get / config_set | View / change runtime config subset |
| /admin blacklist_add | Blacklist a user from creating tickets |
| /admin perms_check | Check bot permissions |
| /health | Bot health & metrics |

Legacy prefix versions exist with `!` for most commands.

## Status Prefix Logic
Thread names are normalized so only one status prefix exists. When status changes, any existing recognized prefix is replaced.

## Transcripts
When closing a ticket:
- Private: Always generates transcript (TXT+HTML) and posts to log channel, DM optional.
- Public: Transcript included on closure after resolution selection (or timeout).

## Duplicate Detection
The last 25 ticket titles are compared using RapidFuzz token_set_ratio. If similarity >= `DUPLICATE_SIMILARITY` the user is informed, but ticket still opens.

## Configuration (.env)
See `.env.example` for full list. Some values (e.g., `anonymize_public`, `ticket_cooldown_seconds`, `duplicate_similarity`) can be adjusted at runtime.

## Roadmap / Possible Extensions
- Web dashboard & REST API
- Internationalization layer
- Enhanced analytics persistence
- More granular permission / category mapping

## License
MIT