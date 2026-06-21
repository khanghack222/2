"""Dictionary Plugin - Dictionary lookup commands"""
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from core.plugin import BasePlugin


class DictionaryPlugin(BasePlugin):
    """Dictionary commands plugin"""

    name = "dictionary"
    description = "Dictionary lookup commands"
    commands = ["dict", "dictionary"]

    def register_handlers(self, app):
        """Register dictionary command handlers"""
        app.add_handler(CommandHandler("dict", self.dict_command))
        app.add_handler(CommandHandler("dictionary", self.dict_command))

    async def dict_command(self, update: Update, context: CallbackContext):
        """Handle /dict command"""
        user_id = update.effective_user.id

        if not context.args:
            await update.effective_message.reply_text(
                "❌ Cách dùng: /dict <từ>\n\n"
                "Ví dụ: /dict hello"
            )
            return

        word = context.args[0].lower()

        try:
            # Check cache first
            cache_key = f"dict:{word}"
            cached = self.context.cache.get(cache_key)

            if cached:
                await update.effective_message.reply_text(cached, parse_mode="Markdown")
                return

            # Fetch from Free Dictionary API
            definitions = await self._get_definitions(word)

            if not definitions:
                await update.effective_message.reply_text(
                    f"❌ Không tìm thấy định nghĩa cho: {word}"
                )
                return

            # Format message
            message = f"📚 **{word.capitalize()}**\n\n"

            for i, definition in enumerate(definitions[:3], 1):
                part_of_speech = definition.get('partOfSpeech', 'N/A')
                meaning = definition.get('definition', 'N/A')
                example = definition.get('example', '')

                message += f"**{i}.** _{part_of_speech}_\n"
                message += f"   {meaning}\n"

                if example:
                    message += f"   💬 _{example}_\n"

                message += "\n"

            # Cache for 10 minutes
            self.context.cache.set(cache_key, message, ttl=600)

            await update.effective_message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            await update.effective_message.reply_text(
                f"❌ Lỗi khi tra từ điển: {word}"
            )
            print(f"Dictionary error: {e}")

    async def _get_definitions(self, word: str) -> list:
        """Fetch definitions from Free Dictionary API"""
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"

        try:
            data = await self.context.http_client.get(url)

            if not data or not isinstance(data, list):
                return []

            definitions = []

            for entry in data:
                meanings = entry.get('meanings', [])

                for meaning in meanings:
                    part_of_speech = meaning.get('partOfSpeech', '')
                    defs = meaning.get('definitions', [])

                    for defn in defs[:2]:  # Limit to 2 definitions per part of speech
                        definitions.append({
                            'partOfSpeech': part_of_speech,
                            'definition': defn.get('definition', ''),
                            'example': defn.get('example', '')
                        })

            return definitions

        except Exception as e:
            print(f"Dictionary API error: {e}")
            return []
