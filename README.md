## Grok Discord Bot

A sarcastic Discord bot plus a comprehensive FastAPI admin UI backed by SQLite. The bot supports `!ask` for chat completions and `!image` for image generation with Grok, auto-approve queues, and per-guild rate/budget enforcement.

### Quickstart

1. Install deps (Python 3.10+):
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Set env vars:
   ```bash
   export DISCORD_BOT_TOKEN=your_bot_token
   export GROK_API_KEY=your_grok_api_key
   export DATABASE_PATH=grok_bot.sqlite3   # optional
   ```
3. Run the bot:
   ```bash
   python -m grok_bot.bot
   ```
4. Run the web UI (in another terminal):
   ```bash
   uvicorn grok_bot.web:app --host 0.0.0.0 --port 8000
   ```
5. Access the admin UI at `http://localhost:8000`

### Admin UI Authentication

The UI prompts for your Discord user ID on first visit and stores it in localStorage. To grant yourself admin access:

```bash
sqlite3 grok_bot.sqlite3 "INSERT OR IGNORE INTO admin_users (discord_user_id, guild_id) VALUES ('YOUR_ID', 'GUILD_ID');"
```

Alternatively, use the Web UI "Admin Users" page to manage admins (if you're already an admin).

### Features Implemented ✅

**Bot Core**
- ✅ `!ask <text>` for chat completions with Grok
- ✅ `!image <prompt>` for image generation  
- ✅ Sarcastic personality via configurable system prompt
- ✅ Input validation (empty, short, trivial, gibberish, duplicates)
- ✅ Per-guild rate limits (configurable window and max requests)
- ✅ Daily token budgets (user and guild level)
- ✅ Daily image budgets (user and guild level)
- ✅ Auto-approve workflow with admin queue
- ✅ Grok API integration (OpenAI-compatible endpoints)

### Docker Compose

You can run both the Web UI and bot simultaneously using Docker Compose.
1. Copy the example env file and edit values:
```bash
cp .env.example .env
# Edit .env and fill in DISCORD_BOT_TOKEN and GROK_API_KEY (if available)
```
2. Create a `data` directory for the SQLite database and any persistent files:
```bash
mkdir -p data
```
3. Build and run the stack:
```bash
docker compose up --build
```
4. The Web UI should be available at `http://localhost:8000`.

Notes:
- If `DISCORD_BOT_TOKEN` is not provided, the bot service may exit early; the Web UI will continue to run, and Grok responses will be stubbed if `GROK_API_KEY` is not set.
- If Docker is not available on your system, please install Docker Desktop for macOS.

**Admin Web UI**
- ✅ 6 dedicated pages: Overview, Configuration, Approval Queue, History, Analytics, Admin Users
- ✅ Responsive design (mobile, tablet, desktop)
- ✅ Dark mode support
- ✅ Interactive charts (status breakdown pie chart)
- ✅ Searchable message history with filters
- ✅ Configuration editor for all guild settings
- ✅ Approval workflow (approve via Grok, manual reply, or reject)
- ✅ Admin user management per guild

**Database & Logging**
- ✅ SQLite with WAL mode for concurrent access
- ✅ Complete audit trail in message_log
- ✅ Per-guild and per-user daily usage tracking
- ✅ Token cost estimation
- ✅ Error logging and status tracking

**Testing & Documentation**
- ✅ 20+ comprehensive tests covering all features
- ✅ Complete IMPLEMENTATION.md specification checklist
- ✅ Production-ready error handling
- ✅ Security best practices (secrets in env vars, no logging of tokens)

### Testing

Run the test suite:
```bash
pytest tests/ -v
```

Tests cover:
- Spam validation and filtering
- Duplicate detection
- Rate limiting
- Budget enforcement
- Auto-approve workflow
- Configuration management
- Admin user functionality
- Message logging

### Documentation

- `SPECIFICATION.md` - Full specification from product requirements
- `IMPLEMENTATION.md` - Complete checklist of what was implemented
- `CHANGES.md` - Summary of all modifications made
- `COMPLETION_SUMMARY.md` - Overview of enhancements and status

### File Structure

```
src/grok_bot/
├── bot.py               # Discord bot commands
├── service.py           # Request processor logic
├── database.py          # SQLite data layer
├── web.py               # FastAPI Web UI backend
├── grok_client.py       # Grok API client
├── discord_api.py       # Discord message sending
├── config.py            # Settings management
├── spam.py              # Input validation
└── rate_limits.py       # Rate limit enforcement

templates/
├── base.html            # Base layout with navigation
├── overview.html        # Dashboard
├── config.html          # Settings editor
├── queue.html           # Approval queue
├── history.html         # Message history
├── analytics.html       # Analytics & charts
└── admins.html          # Admin management

static/
└── style.css            # Comprehensive styling (700+ lines)

tests/
├── test_spam.py         # Validation tests
├── test_duplicate.py    # Duplicate detection
└── test_comprehensive.py # 20+ feature tests
```

### Configuration

Edit settings via Web UI or database:
- Rate limits (per command, per window)
- Daily budgets (tokens, images)
- System prompt (personality)
- Temperature and max tokens for Grok
- Auto-approve enabled/disabled
- Admin bypass settings

All settings are configurable per guild via the Configuration page.

### Architecture

- **Bot Process**: Discord.py bot with command handlers
- **Web Process**: FastAPI application with async database
- **Shared Database**: SQLite with WAL mode for concurrent read/write
- **Separation**: Can run bot and web on same or different processes

Both processes share the same SQLite database file and access guild configurations and message logs.

### Environment Variables

- `DISCORD_BOT_TOKEN` - Your Discord bot token (required)
- `GROK_API_KEY` - Your Grok API key (required for real responses)
- `GROK_API_BASE` - Grok API base URL (default: https://api.x.ai/v1)
- `GROK_CHAT_MODEL` - Chat model name (default: grok-beta)
- `GROK_IMAGE_MODEL` - Image model name (default: grok-image-1)
- `DATABASE_PATH` - SQLite database path (default: grok_bot.sqlite3)
- `WEB_HOST` - Web server host (default: 0.0.0.0)
- `WEB_PORT` - Web server port (default: 8000)
- `MAX_PROMPT_CHARS` - Max prompt length (default: 4000)

### Production Deployment

1. Set environment variables in production environment
2. Create SQLite database: `python -m grok_bot.bot` (one-time)
3. Run bot and Web UI processes (can be same or separate instances)
4. Access Web UI at configured host/port
5. Add admins via SQL or Web UI
6. Configure guild settings via Web UI

For better production reliability, consider:
- Running bot and web UI in separate processes
- Using a process manager (systemd, supervisor)
- Monitoring database size and archiving old messages
- Setting up error alerting

### Known Limitations

- Requires manual Discord user ID for first admin setup (can add via Web UI after that)
- No Discord OAuth (can be implemented for better UX)
- Single bot instance per database (could be extended for multiple bots)
- No exponential backoff retry logic (simple error handling)

### Future Enhancements

- Discord OAuth authentication
- 30-day token usage charts
- Top users by consumption ranking
- Exponential backoff retry logic
- Admin audit log table
- Cost estimation with configurable pricing
- Webhook integration for monitoring
