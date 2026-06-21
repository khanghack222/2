"""
Menu Manager - Interactive menu system
Pattern: Centralized menu management with sections
"""
from typing import Dict, List, Optional, Callable, Any
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext


class MenuSection:
    """Represents a menu section with buttons"""

    def __init__(
        self,
        name: str,
        title: str,
        description: str = "",
        icon: str = "📋"
    ):
        self.name = name
        self.title = title
        self.description = description
        self.icon = icon
        self.buttons: List[Dict[str, Any]] = []

    def add_button(
        self,
        text: str,
        callback_data: str,
        row: Optional[int] = None
    ) -> "MenuSection":
        """
        Add a button to this section.

        Args:
            text: Button text
            callback_data: Callback data
            row: Optional row position

        Returns:
            Self for chaining
        """
        self.buttons.append({
            "text": text,
            "callback_data": callback_data,
            "row": row
        })
        return self


class MenuManager:
    """
    Manages interactive menus with sections and buttons.
    Provides a clean way to create navigation menus.
    """

    def __init__(self):
        self._sections: Dict[str, MenuSection] = {}
        self._callbacks: Dict[str, Callable] = {}

    def add_section(
        self,
        name: str,
        title: str,
        description: str = "",
        icon: str = "📋"
    ) -> MenuSection:
        """
        Add a menu section.

        Args:
            name: Section identifier
            title: Section title
            description: Section description
            icon: Section icon

        Returns:
            Created MenuSection
        """
        section = MenuSection(name, title, description, icon)
        self._sections[name] = section
        return section

    def get_section(self, name: str) -> Optional[MenuSection]:
        """
        Get a menu section by name.

        Args:
            name: Section name

        Returns:
            MenuSection or None
        """
        return self._sections.get(name)

    def register_callback(
        self,
        callback_data: str,
        handler: Callable
    ) -> None:
        """
        Register a callback handler.

        Args:
            callback_data: Callback data identifier
            handler: Async handler function
        """
        self._callbacks[callback_data] = handler

    def create_main_menu(
        self,
        columns: int = 2
    ) -> InlineKeyboardMarkup:
        """
        Create main menu with all sections.

        Args:
            columns: Number of columns

        Returns:
            InlineKeyboardMarkup
        """
        keyboard = []
        row = []

        for section in self._sections.values():
            button = InlineKeyboardButton(
                f"{section.icon} {section.title}",
                callback_data=f"menu:{section.name}"
            )
            row.append(button)

            if len(row) >= columns:
                keyboard.append(row)
                row = []

        if row:
            keyboard.append(row)

        return InlineKeyboardMarkup(keyboard)

    def create_section_menu(
        self,
        section_name: str,
        columns: int = 1
    ) -> Optional[InlineKeyboardMarkup]:
        """
        Create menu for a specific section.

        Args:
            section_name: Section name
            columns: Number of columns

        Returns:
            InlineKeyboardMarkup or None
        """
        section = self._sections.get(section_name)
        if not section:
            return None

        keyboard = []
        row = []

        for button_data in section.buttons:
            button = InlineKeyboardButton(
                button_data["text"],
                callback_data=button_data["callback_data"]
            )
            row.append(button)

            if len(row) >= columns:
                keyboard.append(row)
                row = []

        if row:
            keyboard.append(row)

        # Add back button
        keyboard.append([
            InlineKeyboardButton("◀️ Quay lại", callback_data="menu:main")
        ])

        return InlineKeyboardMarkup(keyboard)

    async def handle_callback(
        self,
        update: Update,
        context: CallbackContext
    ) -> bool:
        """
        Handle menu callback.

        Args:
            update: Telegram update
            context: Telegram context

        Returns:
            True if handled
        """
        query = update.callback_query
        if not query or not query.data:
            return False

        data = query.data

        # Handle menu navigation
        if data.startswith("menu:"):
            section_name = data[5:]

            if section_name == "main":
                await query.edit_message_text(
                    "📋 **Menu chính**\n\nChọn một mục:",
                    reply_markup=self.create_main_menu(),
                    parse_mode="Markdown"
                )
                return True

            section = self._sections.get(section_name)
            if section:
                text = f"{section.icon} **{section.title}**\n\n"
                if section.description:
                    text += f"{section.description}\n\n"
                text += "Chọn một tùy chọn:"

                await query.edit_message_text(
                    text,
                    reply_markup=self.create_section_menu(section_name),
                    parse_mode="Markdown"
                )
                return True

        # Handle registered callbacks
        if data in self._callbacks:
            handler = self._callbacks[data]
            await handler(update, context)
            return True

        return False
