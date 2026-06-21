"""
Plugin Registry - Auto-discovery and registration system
Pattern: Plugin architecture with automatic discovery
"""
import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Dict, Type, List, Optional
from telegram.ext import Application

from core.context import AppContext


class BasePlugin:
    """
    Base class for all plugins.
    Plugins must inherit from this class and implement required methods.
    """

    name: str = "unnamed"
    description: str = "No description"
    commands: List[str] = []

    def __init__(self, context: AppContext):
        """
        Initialize plugin with application context.

        Args:
            context: Application context with all services
        """
        self.context = context

    async def initialize(self) -> None:
        """
        Called when plugin is loaded. Override for custom initialization.
        """
        pass

    async def shutdown(self) -> None:
        """
        Called when plugin is unloaded. Override for cleanup.
        """
        pass

    def register_handlers(self, app: Application) -> None:
        """
        Register command handlers with the application.
        Must be implemented by subclasses.

        Args:
            app: Telegram application instance
        """
        raise NotImplementedError("Plugins must implement register_handlers")


class PluginRegistry:
    """
    Registry for managing plugins with auto-discovery.
    Similar to 9Router's provider registry pattern.
    """

    def __init__(self, context: AppContext):
        """
        Initialize plugin registry.

        Args:
            context: Application context
        """
        self.context = context
        self._plugins: Dict[str, BasePlugin] = {}
        self._plugin_classes: Dict[str, Type[BasePlugin]] = {}

    def register(self, plugin_class: Type[BasePlugin]) -> None:
        """
        Register a plugin class.

        Args:
            plugin_class: Plugin class to register
        """
        if not inspect.isclass(plugin_class):
            raise TypeError(f"{plugin_class} is not a class")

        if not issubclass(plugin_class, BasePlugin):
            raise TypeError(f"{plugin_class} is not a BasePlugin subclass")

        name = getattr(plugin_class, 'name', plugin_class.__name__)
        self._plugin_classes[name] = plugin_class

    def discover(self, package_path: str) -> None:
        """
        Auto-discover plugins in a package.

        Args:
            package_path: Python package path (e.g., 'plugins')
        """
        package = importlib.import_module(package_path)
        package_dir = Path(package.__file__).parent

        for module_info in pkgutil.iter_modules([str(package_dir)]):
            if module_info.name.startswith('_'):
                continue

            try:
                module = importlib.import_module(f"{package_path}.{module_info.name}")

                # Find all BasePlugin subclasses in the module
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (issubclass(obj, BasePlugin) and
                        obj is not BasePlugin and
                        obj.__module__ == module.__name__):
                        self.register(obj)

            except Exception as e:
                print(f"Warning: Failed to load plugin {module_info.name}: {e}")

    async def load_plugin(self, name: str) -> Optional[BasePlugin]:
        """
        Load and initialize a specific plugin.

        Args:
            name: Plugin name

        Returns:
            Loaded plugin instance or None
        """
        if name in self._plugins:
            return self._plugins[name]

        if name not in self._plugin_classes:
            print(f"Plugin not found: {name}")
            return None

        try:
            plugin_class = self._plugin_classes[name]
            plugin = plugin_class(self.context)
            await plugin.initialize()
            self._plugins[name] = plugin
            print(f"Loaded plugin: {name}")
            return plugin
        except Exception as e:
            print(f"Failed to load plugin {name}: {e}")
            return None

    async def load_all(self) -> Dict[str, BasePlugin]:
        """
        Load all registered plugins.

        Returns:
            Dictionary of loaded plugins
        """
        for name in self._plugin_classes:
            await self.load_plugin(name)

        return self._plugins

    async def unload_plugin(self, name: str) -> bool:
        """
        Unload a specific plugin.

        Args:
            name: Plugin name

        Returns:
            True if unloaded successfully
        """
        if name not in self._plugins:
            return False

        try:
            plugin = self._plugins[name]
            await plugin.shutdown()
            del self._plugins[name]
            print(f"Unloaded plugin: {name}")
            return True
        except Exception as e:
            print(f"Failed to unload plugin {name}: {e}")
            return False

    async def unload_all(self) -> None:
        """
        Unload all plugins.
        """
        for name in list(self._plugins.keys()):
            await self.unload_plugin(name)

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        """
        Get a loaded plugin by name.

        Args:
            name: Plugin name

        Returns:
            Plugin instance or None
        """
        return self._plugins.get(name)

    def list_plugins(self) -> List[str]:
        """
        List all registered plugin names.

        Returns:
            List of plugin names
        """
        return list(self._plugin_classes.keys())

    def list_loaded(self) -> List[str]:
        """
        List all loaded plugin names.

        Returns:
            List of loaded plugin names
        """
        return list(self._plugins.keys())
