"""Clear History Plugin - Clear AI conversation history"""
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from core.plugin import BasePlugin


class ClearHistoryPlugin(BasePlugin):
    """Clear conversation history plugin"""

    name = "clear_history"
    description = "Clear AI conversation history"
    commands = ["clear", "xoa"]

    def register_handlers(self, app):
        """Register clear history command handlers"""
        app.add_handler(CommandHandler("clear", self.clear_command))
        app.add_handler(CommandHandler("xoa", self.clear_command))  # Vietnamese alias

    async def clear_command(self, update: Update, context: CallbackContext):
        """Handle /clear command"""
        user_id = update.effective_user.id

        # Get AI chat plugin and clear history
        ai_plugin = context.bot_data.get('ai_chat_plugin')
        if ai_plugin:
            ai_plugin.clear_history(user_id)
            await update.message.reply_text(
                "✅ Đã xóa lịch sử trò chuyện AI!\n\n"
                "Cuộc trò chuyện tiếp theo sẽ bắt đầu từ đầu."
            )
        else:
            await update.message.reply_text(
                "⚠️ Không tìm thấy AI chat plugin."
            )
