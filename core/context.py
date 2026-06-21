"""
Application Context - Dependency Injection Container
Pattern: Centralized access to all services and repositories
"""
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from data.database import Database
    from data.repositories import Repositories
    from services.cache import CacheService
    from services.reminder import ReminderService
    from services.password import PasswordService
    from ai.router import AIRouter
    from http_client.client import HttpClient
    from core.middleware import MiddlewarePipeline
    from core.menu import MenuManager
    from core.i18n import Translator
    from core.config import Config


class AppContext:
    """
    Centralized dependency injection container.
    All plugins and services access shared resources through this context.
    """

    def __init__(self):
        self._config: Optional["Config"] = None
        self._db: Optional["Database"] = None
        self._repos: Optional["Repositories"] = None
        self._cache: Optional["CacheService"] = None
        self._reminder_service: Optional["ReminderService"] = None
        self._password_service: Optional["PasswordService"] = None
        self._ai_router: Optional["AIRouter"] = None
        self._http_client: Optional["HttpClient"] = None
        self._pipeline: Optional["MiddlewarePipeline"] = None
        self._menu_manager: Optional["MenuManager"] = None
        self._translator: Optional["Translator"] = None

    @property
    def config(self) -> "Config":
        if not self._config:
            raise RuntimeError("Config not initialized")
        return self._config

    @config.setter
    def config(self, value: "Config"):
        self._config = value

    @property
    def db(self) -> "Database":
        if not self._db:
            raise RuntimeError("Database not initialized")
        return self._db

    @db.setter
    def db(self, value: "Database"):
        self._db = value

    @property
    def repos(self) -> "Repositories":
        if not self._repos:
            raise RuntimeError("Repositories not initialized")
        return self._repos

    @repos.setter
    def repos(self, value: "Repositories"):
        self._repos = value

    @property
    def cache(self) -> "CacheService":
        if not self._cache:
            raise RuntimeError("Cache not initialized")
        return self._cache

    @cache.setter
    def cache(self, value: "CacheService"):
        self._cache = value

    @property
    def reminder_service(self) -> "ReminderService":
        if not self._reminder_service:
            raise RuntimeError("ReminderService not initialized")
        return self._reminder_service

    @reminder_service.setter
    def reminder_service(self, value: "ReminderService"):
        self._reminder_service = value

    @property
    def password_service(self) -> "PasswordService":
        if not self._password_service:
            raise RuntimeError("PasswordService not initialized")
        return self._password_service

    @password_service.setter
    def password_service(self, value: "PasswordService"):
        self._password_service = value

    @property
    def ai_router(self) -> "AIRouter":
        if not self._ai_router:
            raise RuntimeError("AIRouter not initialized")
        return self._ai_router

    @ai_router.setter
    def ai_router(self, value: "AIRouter"):
        self._ai_router = value

    @property
    def http_client(self) -> "HttpClient":
        if not self._http_client:
            raise RuntimeError("HttpClient not initialized")
        return self._http_client

    @http_client.setter
    def http_client(self, value: "HttpClient"):
        self._http_client = value

    @property
    def pipeline(self) -> "MiddlewarePipeline":
        if not self._pipeline:
            raise RuntimeError("Pipeline not initialized")
        return self._pipeline

    @pipeline.setter
    def pipeline(self, value: "MiddlewarePipeline"):
        self._pipeline = value

    @property
    def menu_manager(self) -> "MenuManager":
        if not self._menu_manager:
            raise RuntimeError("MenuManager not initialized")
        return self._menu_manager

    @menu_manager.setter
    def menu_manager(self, value: "MenuManager"):
        self._menu_manager = value

    @property
    def translator(self) -> "Translator":
        if not self._translator:
            raise RuntimeError("Translator not initialized")
        return self._translator

    @translator.setter
    def translator(self, value: "Translator"):
        self._translator = value
