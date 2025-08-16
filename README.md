# PRM Discord Bot

A Discord bot for ProjektasMiestas.lt community that provides ticket management functionality.

## What it does
- Creates support tickets (public threads or private channels)
- Manages ticket status and lifecycle
- Provides moderation and admin tools
- Generates transcripts when tickets are closed

## Quick Start
1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and configure your Discord bot settings
4. Run: `python bot.py`

## Main Commands
- `/ticket_open` - Create a new support ticket
- `/ticket_close` - Close a ticket
- `/ticket_status` - Update ticket status
- `/help_tickets` - Show available commands

## Requirements
- Python 3.8+
- Discord bot token with proper permissions
- Configured channels for tickets and logs

## License
MIT
