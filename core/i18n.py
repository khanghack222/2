"""
Internationalization (i18n) - Multi-language support
Pattern: Centralized translation management
"""
import json
from pathlib import Path
from typing import Dict, Optional


class Translator:
    """
    Manages translations for multiple languages.
    Loads translations from JSON files in i18n/ directory.
    """

    def __init__(self, default_language: str = "vi"):
        """
        Initialize translator.

        Args:
            default_language: Default language code
        """
        self.default_language = default_language
        self._translations: Dict[str, Dict[str, str]] = {}
        self._user_languages: Dict[int, str] = {}
        self._load_translations()

    def _load_translations(self) -> None:
        """Load all translation files from i18n/ directory"""
        i18n_dir = Path(__file__).parent.parent / "i18n"

        if not i18n_dir.exists():
            print(f"Warning: i18n directory not found: {i18n_dir}")
            return

        for json_file in i18n_dir.glob("*.json"):
            lang_code = json_file.stem
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    self._translations[lang_code] = json.load(f)
                print(f"Loaded translations: {lang_code}")
            except Exception as e:
                print(f"Failed to load {json_file}: {e}")

    def set_user_language(self, user_id: int, language: str) -> None:
        """
        Set language preference for a user.

        Args:
            user_id: Telegram user ID
            language: Language code (e.g., 'vi', 'en')
        """
        self._user_languages[user_id] = language

    def get_user_language(self, user_id: int) -> str:
        """
        Get language preference for a user.

        Args:
            user_id: Telegram user ID

        Returns:
            Language code
        """
        return self._user_languages.get(user_id, self.default_language)

    def translate(
        self,
        key: str,
        user_id: Optional[int] = None,
        language: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Translate a key to the appropriate language.

        Args:
            key: Translation key (e.g., 'weather.city_not_found')
            user_id: Optional user ID to get their language preference
            language: Optional language override
            **kwargs: Format arguments for the translation

        Returns:
            Translated string or key if not found
        """
        # Determine language
        if language:
            lang = language
        elif user_id:
            lang = self.get_user_language(user_id)
        else:
            lang = self.default_language

        # Get translations for the language
        translations = self._translations.get(lang, {})

        # Navigate nested keys (e.g., 'weather.city_not_found')
        value = translations
        for part in key.split('.'):
            if isinstance(value, dict):
                value = value.get(part)
            else:
                value = None
                break

        # Fallback to default language
        if value is None and lang != self.default_language:
            translations = self._translations.get(self.default_language, {})
            value = translations
            for part in key.split('.'):
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    value = None
                    break

        # Fallback to key itself
        if value is None:
            return key

        # Format with kwargs
        if kwargs and isinstance(value, str):
            try:
                return value.format(**kwargs)
            except (KeyError, ValueError):
                return value

        return value

    def t(
        self,
        key: str,
        user_id: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        Shorthand for translate().

        Args:
            key: Translation key
            user_id: Optional user ID
            **kwargs: Format arguments

        Returns:
            Translated string
        """
        return self.translate(key, user_id=user_id, **kwargs)

    def get_available_languages(self) -> list[str]:
        """
        Get list of available languages.

        Returns:
            List of language codes
        """
        return list(self._translations.keys())

    def has_language(self, language: str) -> bool:
        """
        Check if a language is available.

        Args:
            language: Language code

        Returns:
            True if available
        """
        return language in self._translations
