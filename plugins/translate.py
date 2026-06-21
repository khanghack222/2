"""Translate Plugin - Text translation"""
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from core.plugin import BasePlugin


class TranslatePlugin(BasePlugin):
    """Translation commands plugin"""

    name = "translate"
    description = "Text translation commands"
    commands = ["translate", "dich"]

    def register_handlers(self, app):
        """Register translate command handlers"""
        app.add_handler(CommandHandler("translate", self.translate_command))
        app.add_handler(CommandHandler("dich", self.translate_command))

    async def translate_command(self, update: Update, context: CallbackContext):
        """Handle /translate command"""
        user_id = update.effective_user.id
        t = self.context.translator.t

        if not context.args:
            await update.effective_message.reply_text(
                "❌ Cách dùng: /translate <văn bản>\n\n"
                "Ví dụ: /translate Hello world"
            )
            return

        text = " ".join(context.args)

        try:
            # Call Google Translate API
            translated = await self._translate_text(text, target_lang="vi")

            message = f"🌐 **Dịch:**\n\n"
            message += f"**Gốc:** {text}\n"
            message += f"**Dịch:** {translated}"

            await update.effective_message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            await update.effective_message.reply_text(
                t('translate.error', user_id)
            )
            print(f"Translate error: {e}")

    async def _translate_text(self, text: str, target_lang: str = "vi") -> str:
        """Translate text using Google Translate API"""
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": target_lang,
            "dt": "t",
            "q": text
        }

        try:
            response = await self.context.http_client.get(url, params=params)

            # Parse response
            if isinstance(response, list) and len(response) > 0:
                translations = response[0]
                if isinstance(translations, list):
                    result = "".join(
                        item[0] for item in translations
                        if isinstance(item, list) and len(item) > 0
                    )
                    return result

            return text

        except Exception as e:
            raise Exception(f"Translation failed: {str(e)}")
