"""
Main Application Entry Point
Modular Telegram Bot with Plugin Architecture
"""
import asyncio
import logging
from telegram.ext import Application, CallbackQueryHandler

from core.config import Config
from core.context import AppContext
from core.plugin import PluginRegistry
from core.menu import MenuManager
from core.i18n import Translator
from core.middleware import MiddlewarePipeline
from core.middlewares import RateLimitMiddleware, ErrorHandlingMiddleware, LoggingMiddleware

from data.database import Database
from data.repositories import Repositories
from services.cache import CacheService
from services.reminder import ReminderService
from services.password import PasswordService
from ai.router import AIRouter
from ai.providers import OpenRouterProvider, GroqProvider, OpenAIProvider
from http.client import HttpClient

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def initialize_app() -> tuple[Application, AppContext]:
    """Initialize the Telegram bot application"""

    # Load configuration
    config = Config.from_env()

    # Validate config
    warnings = config.validate()
    for warning in warnings:
        logger.warning(f"Config warning: {warning}")

    # Initialize database
    database = Database(config.db_path)
    await database.connect()
    await database.init_schema()

    # Initialize repositories
    repos = Repositories(database)

    # Initialize services
    cache_service = CacheService(max_size=config.cache_size, default_ttl=config.cache_ttl)
    reminder_service = ReminderService(repos.reminder)
    password_service = PasswordService(repos.password, config.password_encryption_key)

    # Initialize AI providers
    providers = []

    # Add OpenRouter if configured
    if config.openrouter_api_key:
        providers.append(OpenRouterProvider(config.openrouter_api_key))
        logger.info("✓ OpenRouter provider loaded")

    # Add Groq if configured
    if config.groq_api_key:
        providers.append(GroqProvider(config.groq_api_key))
        logger.info("✓ Groq provider loaded")

    # Add OpenAI as fallback
    if config.openai_api_key:
        providers.append(OpenAIProvider(config.openai_api_key))
        logger.info("✓ OpenAI provider loaded")

    ai_router = AIRouter(providers)
    logger.info(f"✓ AI Router initialized with {len(providers)} providers")

    # Initialize HTTP client
    http_client = HttpClient(
        timeout=config.http_timeout,
        max_retries=config.http_max_retries,
        retry_delay=config.http_retry_delay
    )
    logger.info("✓ HTTP client initialized")

    # Initialize i18n
    translator = Translator()
    logger.info("✓ Translator initialized")

    # Initialize menu manager
    menu_manager = MenuManager()
    logger.info("✓ Menu manager initialized")

    # Create application context
    context = AppContext()
    context.config = config
    context.database = database
    context.repositories = repos
    context.cache = cache_service
    context.reminder_service = reminder_service
    context.password_service = password_service
    context.ai_router = ai_router
    context.http_client = http_client
    context.translator = translator
    context.menu_manager = menu_manager

    # Initialize middleware pipeline
    pipeline = MiddlewarePipeline()
    pipeline.use(LoggingMiddleware(context))
    pipeline.use(RateLimitMiddleware(
        max_requests=config.rate_limit_max_requests,
        window_seconds=config.rate_limit_window
    ))
    pipeline.use(ErrorHandlingMiddleware(context))
    context.pipeline = pipeline
    logger.info("✓ Middleware pipeline configured")

    # Create Telegram application
    app = Application.builder().token(config.bot_token).build()
    context.bot = app.bot

    # Register plugins
    plugin_registry = PluginRegistry(context)

    # Discover and register all plugins
    plugin_registry.discover("plugins")
    logger.info(f"✓ Discovered {len(plugin_registry.get_plugins())} plugins")

    # Load and register all plugin handlers
    await plugin_registry.load_all()
    for plugin in plugin_registry.get_plugins():
        plugin.register_handlers(app)
        logger.info(f"✓ Loaded plugin: {plugin.name}")

    # Register menu callback handler
    app.add_handler(CallbackQueryHandler(menu_manager.handle_callback))
    logger.info("✓ Menu callback handler registered")

    # Apply middleware to all command handlers
    # Note: In python-telegram-bot, we wrap handlers manually
    # For now, middleware will be called within each command

    logger.info("=" * 60)
    logger.info("🤖 Telegram Bot initialized successfully!")
    logger.info(f"📊 Plugins: {len(plugin_registry.get_plugins())}")
    logger.info(f"🧠 AI Providers: {len(providers)}")
    logger.info(f"💾 Database: {config.db_path}")
    logger.info("=" * 60)

    return app, context


async def main():
    """Main entry point"""
    try:
        app, context = await initialize_app()

        # Start polling
        logger.info("🚀 Starting bot polling...")
        await app.initialize()
        await app.start()
        await app.updater.start_polling(allowed_updates=["message", "callback_query"])

        # Keep running
        logger.info("✅ Bot is running! Press Ctrl+C to stop.")

        # Wait forever
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("⏹️  Shutting down...")

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)

    finally:
        # Cleanup
        if 'context' in locals():
            await context.database.close()
            await context.http_client.close()
            logger.info("✓ Cleanup completed")

        if 'app' in locals():
            await app.stop()
            await app.shutdown()
            logger.info("✓ Application stopped")


if __name__ == "__main__":
    asyncio.run(main())
