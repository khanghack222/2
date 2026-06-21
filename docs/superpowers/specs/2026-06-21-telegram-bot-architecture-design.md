# Telegram Bot Design Specification

## Overview

A modular Telegram bot built with Python using patterns inspired by 9Router architecture. The bot uses a plugin-based structure with middleware pipeline, smart AI routing, and health-tracked HTTP clients.

## Architecture

### Core Principles

1. **Plugin Architecture**: Each feature domain (weather, tools, AI, etc.) is a separate plugin
2. **Middleware Pipeline**: Cross-cutting concerns (flood protection, rate limiting, stats, error handling) run as middleware
3. **Smart Routing**: AI providers selected based on health metrics (success rate, latency)
4. **Health Tracking**: HTTP endpoints and AI providers tracked for reliability
5. **Dependency Injection**: AppContext injected into plugins and services
6. **Repository Pattern**: Data access through repository classes

### Project Structure

```
telegram_bot/
├── config.py                    # Centralized config + validation
├── main.py                      # Thin entry point
│
├── core/                        # Framework layer
│   ├── app.py                   # Application builder + lifecycle
│   ├── context.py               # AppContext (DI container)
│   ├── plugin.py                # Plugin registry + auto-discovery
│   ├── middleware.py            # Middleware pipeline engine
│   ├── middlewares.py           # Concrete middleware implementations
│   └── menu.py                  # Interactive menu system
│
├── plugins/                     # Command modules
│   ├── base.py                  # BasePlugin interface
│   ├── system.py                # /start, /help, /id, /status, /restart, /lang
│   ├── utility.py               # /weather, /translate, /shorten, /qr, /ip, /screenshot, /proxy, /bypass
│   ├── tools.py                 # /calc, /code, /password*, /editpass, /delpass
│   ├── education.py             # /van, /dictionary, /wiki
│   ├── finance.py               # /crypto, /tygia, /stock
│   ├── entertainment.py         # /joke, /anime, /meme
│   ├── calendar.py              # /lich, /remind, /list, /cancel
│   ├── ai_chat.py               # /ask, /clear
│   ├── tiktok.py                # /tiktok* (8 commands)
│   ├── media.py                 # /yt, /music, /news
│   ├── stats.py                 # /stats, /myusage
│   └── admin.py                 # /kick, /ban, /unban, /mute, /unmute
│
├── data/                        # Unified data layer
│   ├── database.py              # SQLite connection + WAL + migrations
│   ├── repositories.py          # Repository classes per entity
│   └── migrations.py            # Schema versioning
│
├── services/                    # Business logic
│   ├── reminder.py              # Reminder scheduling
│   ├── password.py              # Password encryption
│   └── cache.py                 # TTL cache + LRU
│
├── ai/                          # AI Provider system
│   ├── provider.py              # BaseProvider interface
│   ├── router.py                # Smart router + fallback + circuit breaker
│   ├── registry.py              # Provider registry + health tracking
│   ├── history.py               # Chat history + token management
│   ├── streaming.py             # SSE streaming to Telegram
│   └── providers/
│       ├── ninerouter.py        # 9Router provider
│       ├── groq.py              # Groq provider
│       └── openai_provider.py   # OpenAI provider
│
├── i18n/                        # Internationalization
│   ├── __init__.py              # Translator engine
│   ├── vi.json                  # Vietnamese strings
│   └── en.json                  # English strings
│
├── http/                        # HTTP utilities
│   └── client.py                # Async HTTP client + health tracking
│
└── dashboard/                   # Web dashboard
    ├── server.py                # aiohttp web server
    └── templates/
        └── index.html           # Dashboard UI
```

## Design Patterns

### 1. Plugin Architecture

**BasePlugin Interface**:
```python
class BasePlugin(ABC):
    def __init__(self, ctx: AppContext): ...
    def commands(self) -> list[CommandInfo]: ...
    def menu_section(self) -> MenuSection | None: ...
    async def register(self, app: Application): ...
```

**Plugin Registration**:
- Plugins auto-discovered from `plugins/` directory
- Each plugin exports a `Plugin` class inheriting from `BasePlugin`
- `core/plugin.py` scans and instantiates plugins
- Plugins register their own command handlers

**AppContext Injection**:
- Shared dependencies (db, repos, http, i18n, cache, pipeline, ai_router, menu)
- Passed to plugin constructor
- Plugins access services via `self.ctx`

### 2. Middleware Pipeline

**Middleware Interface**:
```python
class Middleware(ABC):
    async def process(self, update, context, next_fn): ...
```

**Pipeline Execution Order**:
1. `FloodProtection` - Block spam (8 msgs/15s)
2. `RateLimiter` - Per-user per-command cooldown
3. `StatsLogger` - Log commands to DB
4. `ErrorHandler` - Catch exceptions, log to DB, notify user

**Handler Wrapping**:
```python
pipeline.wrap(handler_fn)  # Returns wrapped function
```

### 3. Smart AI Routing

**Provider Interface**:
```python
class BaseProvider(ABC):
    async def chat(self, messages, **kwargs) -> ProviderResponse: ...
    async def chat_stream(self, messages, on_chunk, **kwargs) -> ProviderResponse: ...
    def is_configured(self) -> bool: ...
```

**Router Logic**:
1. Filter providers: configured + circuit breaker allows
2. Sort by: success_rate DESC → latency ASC → priority ASC
3. Try each provider with retry logic (exponential backoff)
4. Record success/failure to health metrics
5. Circuit breaker trips after N failures (skip for 60s)

**Circuit Breaker States**:
- `CLOSED` - Normal operation
- `OPEN` - Skip provider (too many failures)
- `HALF_OPEN` - Test one request to check recovery

**Streaming to Telegram**:
- Send placeholder message
- Edit message every 1.5s with accumulated chunks
- Final edit with full response + metadata

### 4. HTTP Client with Health Tracking

**EndpointHealth**:
- Track per-domain: success_rate, avg_latency, total_requests
- Sliding window (last 20 requests)
- `is_healthy` = success_rate >= 50%

**HttpClient Methods**:
- `fetch_json(url)` - GET → JSON
- `fetch_text(url)` - GET → text
- `fetch_bytes(url)` - GET → bytes
- `post_json(url, json_data, headers)` - POST → JSON

All methods record health metrics automatically.

### 5. Repository Pattern

**Repository Classes**:
- `ReminderRepo` - CRUD for reminders
- `PasswordRepo` - CRUD for passwords (encrypted at service layer)
- `StatsRepo` - Command/error logging + statistics
- `AIHistoryRepo` - Per-user chat history
- `VanBlacklistRepo` - Blacklist URLs
- `UserLangRepo` - Per-user language preference

**Database**:
- SQLite with WAL mode
- Batch flush loop (commit every 2s)
- Schema versioning via `migrations.py`

### 6. i18n System

**Translator**:
- Load strings from JSON files (`i18n/vi.json`, `i18n/en.json`)
- Fallback chain: user_lang → "vi" → key
- Placeholder support: `{name}`, `{count}`
- User language stored in DB (`user_lang` table)

**Usage**:
```python
text = self.ctx.i18n.t("weather_header", user_id, place="Hanoi")
```

## Data Flow

### Command Execution

```
User sends /weather hanoi
    ↓
Telegram Update
    ↓
Middleware Pipeline:
  1. FloodProtection - check rate
  2. RateLimiter - check cooldown
  3. StatsLogger - log to DB
  4. ErrorHandler - wrap in try/except
    ↓
Plugin Handler (utility.weather_cmd)
    ↓
Cache Check (self.ctx.cache)
    ↓
HTTP Request (self.ctx.http.fetch_json)
  - Health tracked automatically
    ↓
Parse Response
    ↓
Cache Result
    ↓
Reply to User
```

### AI Chat Flow

```
User sends /ask Python là gì?
    ↓
Load History (ai_history repo)
    ↓
Build Messages (token-aware truncation)
    ↓
Send Placeholder (TelegramStreamer)
    ↓
AI Router:
  - Select best provider (health + latency)
  - Circuit breaker check
  - Retry with backoff on failure
  - Fallback to next provider
    ↓
Stream Response:
  - on_chunk callback
  - Edit message every 1.5s
    ↓
Save History (with token count)
    ↓
Final Edit (full response + metadata)
```

## Configuration

**Config Class** (frozen dataclass):
```python
@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_id: int | None
    router_api_key: str
    router_base_url: str
    router_model: str
    groq_api_key: str
    groq_model: str
    openai_api_key: str
    openai_model: str
    ai_max_tokens: int
    pass_key: str
    port: int
    db_path: str
    bypass_url: str
    bypass_key: str
    default_rate_limit: int
```

**Loading**:
```python
config = Config.from_env()  # Reads .env + os.environ
warnings = config.validate()
```

**No Hardcoded Secrets**:
- All API keys from env vars
- No defaults for sensitive values

## Plugin Examples

### Plugin Count

- **12 plugins** total
- **~100-300 lines** per plugin
- **~2300 lines** total (vs 2845 in monolithic bot.py)

### Plugin Categories

1. `system` - Bot management (6 commands)
2. `utility` - General tools (8 commands)
3. `tools` - Developer tools (8 commands)
4. `education` - Learning (3 commands)
5. `finance` - Market data (3 commands)
6. `entertainment` - Fun (3 commands)
7. `calendar` - Reminders (4 commands)
8. `ai_chat` - AI assistant (2 commands)
9. `tiktok` - TikTok features (8 commands + auto-reply)
10. `media` - YouTube/music/news (3 commands)
11. `stats` - Analytics (2 commands)
12. `admin` - Group admin (5 commands)

## Migration Strategy

### Phase 1: Core Framework
1. Create `core/` package (app, context, plugin, middleware, menu)
2. Create `data/` package (database, repositories, migrations)
3. Create `services/` package (reminder, password, cache)
4. Create `config.py`
5. Create `main.py`

### Phase 2: AI System
1. Create `ai/` package (provider, router, registry, history, streaming)
2. Create `ai/providers/` (ninerouter, groq, openai_provider)

### Phase 3: HTTP + i18n
1. Create `http/client.py`
2. Create `i18n/` package (translator + JSON files)

### Phase 4: Plugins
1. Create `plugins/base.py`
2. Migrate handlers from bot.py to plugin files (one by one)
3. Test each plugin independently

### Phase 5: Integration
1. Update `core/app.py` to wire everything together
2. Migrate menu system
3. Update dashboard with health metrics
4. Full integration testing

### Phase 6: Cleanup
1. Remove old bot.py
2. Update Docker/deploy configs
3. Update documentation

## Key Improvements

| Aspect | Before | After |
|--------|--------|-------|
| **Structure** | 1 file (2845 lines) | 12 plugins (~200 lines each) |
| **Rate Limiting** | Manual decorator on 20/42 commands | Automatic via middleware |
| **Error Handling** | Scattered try/except | Centralized middleware |
| **AI Routing** | Static order | Smart (health + latency) |
| **Circuit Breaker** | None | Auto-skip failing providers |
| **History** | Unbounded | Token-aware truncation |
| **Streaming** | Buffer all | Edit message every 1.5s |
| **HTTP Tracking** | None | Per-endpoint health metrics |
| **Config** | Hardcoded secrets | Env vars + validation |
| **Persistence** | JSON + SQLite (split brain) | SQLite only |
| **Data Access** | Flat functions | Repository classes |
| **i18n** | Hardcoded dict | JSON files + fallback |
| **Testing** | Hard (monolith) | Easy (mock AppContext) |

## Testing Strategy

1. **Unit Tests** - Each plugin, service, repository
2. **Integration Tests** - Middleware pipeline, AI router
3. **Mock AppContext** - Inject fake services
4. **Health Metrics** - Verify tracking works
5. **Circuit Breaker** - Test state transitions

## Dashboard Enhancements

Add to existing dashboard:
- AI provider health (success rate, latency, circuit state)
- HTTP endpoint health (per-domain metrics)
- Middleware stats (flood blocks, rate limits, errors)
- Cache hit rate
- Active reminders count

## Self-Review Checklist

- [x] Placeholder scan: No TBD/TODO items
- [x] Internal consistency: Architecture matches feature descriptions
- [x] Scope check: Focused enough for single implementation plan
- [x] Ambiguity check: All requirements explicit

## Status

**Approved for Implementation**

Next: Create detailed implementation plan, then begin coding.

## Conclusion

This architecture transforms the monolithic bot into a modular, testable, production-ready system using patterns proven in 9Router. The plugin architecture enables easy feature addition, middleware ensures consistent cross-cutting concerns, and smart routing makes AI features resilient.
