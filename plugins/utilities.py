"""Utilities Plugin - Various utility commands"""
import qrcode
import io
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from core.plugin import BasePlugin


class UtilitiesPlugin(BasePlugin):
    """Utility commands plugin"""

    name = "utilities"
    description = "Utility commands"
    commands = ["qr", "shorten", "calc"]

    def register_handlers(self, app):
        """Register utility command handlers"""
        app.add_handler(CommandHandler("qr", self.qr_command))
        app.add_handler(CommandHandler("shorten", self.shorten_command))
        app.add_handler(CommandHandler("calc", self.calc_command))

    async def qr_command(self, update: Update, context: CallbackContext):
        """Handle /qr command - generate QR code"""
        if not context.args:
            await update.effective_message.reply_text(
                "❌ Cách dùng: /qr <nội dung>\n\n"
                "Ví dụ: /qr https://example.com"
            )
            return

        text = " ".join(context.args)

        try:
            # Generate QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(text)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")

            # Convert to bytes
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)

            await update.effective_message.reply_photo(
                photo=img_byte_arr,
                caption=f"📱 QR Code: {text[:50]}{'...' if len(text) > 50 else ''}"
            )

        except Exception as e:
            await update.effective_message.reply_text(
                f"❌ Lỗi khi tạo QR code: {str(e)}"
            )
            print(f"QR error: {e}")

    async def shorten_command(self, update: Update, context: CallbackContext):
        """Handle /shorten command - shorten URL"""
        if not context.args:
            await update.effective_message.reply_text(
                "❌ Cách dùng: /shorten <url>\n\n"
                "Ví dụ: /shorten https://example.com/very/long/url"
            )
            return

        url = context.args[0]

        try:
            # Use TinyURL API
            short_url = await self._shorten_url(url)

            if not short_url:
                await update.effective_message.reply_text(
                    "❌ Không thể rút gọn URL"
                )
                return

            message = f"🔗 **URL Rút gọn:**\n\n"
            message += f"**Gốc:** {url}\n\n"
            message += f"**Ngắn:** {short_url}"

            await update.effective_message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            await update.effective_message.reply_text(
                f"❌ Lỗi khi rút gọn URL: {str(e)}"
            )
            print(f"Shorten error: {e}")

    async def calc_command(self, update: Update, context: CallbackContext):
        """Handle /calc command - simple calculator"""
        if not context.args:
            await update.effective_message.reply_text(
                "❌ Cách dùng: /calc <biểu thức>\n\n"
                "Ví dụ: /calc 2 + 2\n"
                "Ví dụ: /calc 10 * 5\n"
                "Ví dụ: /calc 100 / 4"
            )
            return

        expression = " ".join(context.args)

        try:
            # Safe evaluation using eval with restricted globals
            # Only allow basic math operations
            allowed_names = {
                'abs': abs,
                'round': round,
                'min': min,
                'max': max,
                'sum': sum,
                'pow': pow,
            }

            result = eval(expression, {"__builtins__": {}}, allowed_names)

            message = f"🧮 **Tính toán:**\n\n"
            message += f"`{expression}` = **{result}**"

            await update.effective_message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            await update.effective_message.reply_text(
                f"❌ Biểu thức không hợp lệ: {expression}\n\n"
                f"Lỗi: {str(e)}"
            )

    async def _shorten_url(self, url: str) -> str:
        """Shorten URL using TinyURL"""
        try:
            api_url = f"https://tinyurl.com/api-create.php?url={url}"
            response = await self.context.http_client.get_text(api_url)
            return response.strip() if response else None
        except Exception as e:
            print(f"TinyURL error: {e}")
            return None
