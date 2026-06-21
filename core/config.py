"""
Configuration management with validation
Pattern: Centralized config with env var support
"""
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    """Immutable configuration object"""
    # Required
    bot_token: str

    # Optional with defaults
    admin_id: Optional[int] = None
    db_path: str = "data/bot.db"
    log_level: str = "INFO"

    # API endpoints
    weather_api: str = "https://api.open-meteo.com/v1"
    translate_api: str = "https://translate.googleapis.com/translate_a/single"
    dictionary_api: str = "https://api.dictionaryapi.dev/api/v2"
    crypto_api: str = "https://api.coingecko.com/api/v3"
    tiktok_api: str = "https://www.tikwm.com/api"

    # HTTP settings
    http_timeout: float = 30.0
    http_max_retries: int = 3
    http_retry_delay: float = 1.0

    # AI provider settings
    ai_providers: list = field(default_factory=lambda: [
        {"name": "openrouter", "priority": 1},
        {"name": "groq", "priority": 2},
        {"name": "openai", "priority": 3},
    ])
    ai_circuit_breaker_threshold: int = 3
    ai_circuit_breaker_timeout: float = 60.0

    # Cache settings
    cache_size: int = 1000
    cache_ttl: float = 300.0

    # Rate limiting
    rate_limit_window: float = 60.0
    rate_limit_max_requests: int = 20

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables"""
        bot_token = os.getenv("BOT_TOKEN")
        if not bot_token:
            raise ValueError("BOT_TOKEN environment variable is required")

        admin_id = os.getenv("ADMIN_ID")

        return cls(
            bot_token=bot_token,
            admin_id=int(admin_id) if admin_id else None,
            db_path=os.getenv("DB_PATH", "data/bot.db"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            weather_api=os.getenv("WEATHER_API", "https://api.open-meteo.com/v1"),
            translate_api=os.getenv("TRANSLATE_API", "https://translate.googleapis.com/translate_a/single"),
            dictionary_api=os.getenv("DICTIONARY_API", "https://api.dictionaryapi.dev/api/v2"),
            crypto_api=os.getenv("CRYPTO_API", "https://api.coingecko.com/api/v3"),
            tiktok_api=os.getenv("TIKTOK_API", "https://www.tikwm.com/api"),
            http_timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")),
            http_max_retries=int(os.getenv("HTTP_MAX_RETRIES", "3")),
            http_retry_delay=float(os.getenv("HTTP_RETRY_DELAY", "1.0")),
            ai_circuit_breaker_threshold=int(os.getenv("AI_CIRCUIT_BREAKER_THRESHOLD", "3")),
            ai_circuit_breaker_timeout=float(os.getenv("AI_CIRCUIT_BREAKER_TIMEOUT", "60.0")),
            cache_size=int(os.getenv("CACHE_SIZE", "1000")),
            cache_ttl=float(os.getenv("CACHE_TTL", "300.0")),
            rate_limit_window=float(os.getenv("RATE_LIMIT_WINDOW", "60.0")),
            rate_limit_max_requests=int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "20")),
        )

    def validate(self) -> list[str]:
        """Validate configuration and return list of warnings"""
        warnings = []

        if not os.path.exists(os.path.dirname(self.db_path)):
            warnings.append(f"Database directory does not exist: {os.path.dirname(self.db_path)}")

        if self.log_level not in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            warnings.append(f"Invalid log level: {self.log_level}, using INFO")
            self.log_level = "INFO"

        if self.cache_size < 100:
            warnings.append(f"Cache size too small ({self.cache_size}), using 100")
            self.cache_size = 100

        return warnings
