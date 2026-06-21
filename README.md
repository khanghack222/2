# 🤖 Telegram Bot - Modular Architecture

A modern, modular Telegram bot built with Python using plugin architecture inspired by 9Router patterns.

## ✨ Features

### Core Features
- 🌤 **Weather** - Weather information for any city
- 🌐 **Translate** - Text translation using Google Translate
- 📚 **Dictionary** - English-Vietnamese dictionary
- 💰 **Crypto** - Cryptocurrency prices (BTC, ETH, etc.)
- 📈 **Stock** - Real-time stock prices
- 🤖 **AI Chat** - Multi-provider AI with smart routing
- ⏰ **Reminders** - Set and manage reminders
- 🔐 **Passwords** - Encrypted password storage
- 📊 **Statistics** - Usage statistics and dashboard

### Architecture Highlights
- **Plugin System** - Modular, auto-discovering plugins
- **Middleware Pipeline** - Rate limiting, logging, error handling
- **AI Router** - Multi-provider with circuit breaker pattern
- **Repository Pattern** - Clean data access layer
- **i18n Support** - Multi-language (Vietnamese/English)
- **Health Tracking** - Monitor API health and performance

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

### Installation

1. **Clone and setup**
```bash
cd telegram_bot
pip install -r requirements.txt
```

2. **Configure environment**
```bash
cp .env.example .env
# Edit .env and add your BOT_TOKEN
```

3. **Run the bot**
```bash
python main.py
```

## 📁 Project Structure

```
telegram_bot/
├── core/                    # Core framework
│   ├── config.py           # Configuration management
│   ├── context.py          # Application context (DI container)
│   ├── middleware.py       # Middleware pipeline
│   ├── middlewares.py      # Middleware implementations
│   ├── plugin.py           # Plugin registry
│   ├── menu.py             # Menu manager
│   └── i18n.py             # Internationalization
├── data/                    # Data layer
│   ├── database.py         # SQLite database
│   └── repositories.py     # Repository pattern
├── services/                # Business logic
│   ├── cache.py            # Cache service
│   ├── reminder.py         # Reminder service
│   └── password.py         # Password service
├── ai/                      # AI integration
│   ├── router.py           # AI router with circuit breaker
│   └── providers/          # AI provider implementations
├── http/                    # HTTP client
│   └── client.py           # Async HTTP with health tracking
├── plugins/                 # Bot plugins
│   ├── system.py           # System commands
│   ├── ai_chat.py          # AI commands
│   ├── weather.py          # Weather commands
│   ├── reminder.py         # Reminder commands
│   └── ...                 # More plugins
├── i18n/                    # Translations
│   ├── vi.json             # Vietnamese
│   └── en.json             # English
├── data/                    # Database files
├── main.py                  # Entry point
└── requirements.txt         # Dependencies
```

## 🔧 Configuration

### Required
- `BOT_TOKEN` - Telegram bot token from @BotFather

### Optional API Keys
- `OPENROUTER_API_KEY` - Free AI models (Claude, GPT-4, etc.)
- `GROQ_API_KEY` - Fast inference (Mixtral, Llama)
- `OPENAI_API_KEY` - OpenAI models (GPT-3.5, GPT-4)
- `EXCHANGERATE_API_KEY` - Currency exchange rates
- `ALPHA_VANTAGE_API_KEY` - Stock market data

### Environment Variables
See `.env.example` for all configuration options.

## 🎯 Commands

### System
- `/start` - Start the bot
- `/help` - Show help
- `/menu` - Interactive menu
- `/id` - Show your ID
- `/lang` - Change language

### Utilities
- `/weather <city>` - Get weather
- `/translate <text>` - Translate text
- `/dictionary <word>` - Look up word

### Finance
- `/crypto` - Crypto prices
- `/stock <symbol>` - Stock prices

### AI
- `/ask <question>` - Ask AI

### Productivity
- `/remind <minutes> <text>` - Set reminder
- `/reminders` - List reminders
- `/delremind <id>` - Delete reminder

### Security
- `/password <label>` - Save password
- `/passwords` - List passwords
- `/delpassword <id>` - Delete password

## 🏗️ Architecture Patterns

### Plugin System
```python
class MyPlugin(BasePlugin):
    name = "my_plugin"
    commands = ["mycommand"]

    def register_handlers(self, app):
        app.add_handler(CommandHandler("mycommand", self.handle))

    async def handle(self, update, context):
        # Access services via self.context
        cache = self.context.cache
        ai = self.context.ai_router
        await update.message.reply_text("Hello!")
```

### Middleware Pipeline
```python
pipeline = MiddlewarePipeline()
pipeline.use(LoggingMiddleware(context))
pipeline.use(RateLimitMiddleware(max_requests=20, window_seconds=60))
pipeline.use(ErrorHandlingMiddleware(context))
```

### AI Router with Circuit Breaker
```python
providers = [
    OpenRouterProvider(api_key),
    GroqProvider(api_key),
    OpenAIProvider(api_key)
]
router = AIRouter(providers)
response = await router.chat(messages)
```

## 📊 Dashboard

Access the web dashboard at `http://localhost:8080` to view:
- Command usage statistics
- User activity
- AI provider health
- HTTP client performance

## 🧪 Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html
```

## 🐛 Troubleshooting

### Bot doesn't respond
- Check `BOT_TOKEN` is correct
- Ensure bot is running (`python main.py`)
- Check logs for errors

### AI commands don't work
- Add at least one AI provider API key
- Check provider health in dashboard

### Database errors
- Ensure `data/` directory exists and is writable
- Check `DB_PATH` configuration

## 📝 License

MIT License - feel free to use and modify!

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📞 Support

- Issues: [GitHub Issues](https://github.com/yourusername/telegram-bot/issues)
- Telegram: [@yourusername](https://t.me/yourusername)

---

Built with ❤️ using modern Python patterns
