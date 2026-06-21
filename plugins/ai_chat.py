"""AI Chat Plugin - Ask AI questions"""
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from core.plugin import BasePlugin


class AIChatPlugin(BasePlugin):
    """AI chat plugin"""

    name = "ai_chat"
    description = "AI chatbot commands"
    commands = ["ask"]

    def register_handlers(self, app):
        """Register AI chat command handlers"""
        app.add_handler(CommandHandler("ask", self.ask_command))

    async def ask_command(self, update: Update, context: CallbackContext):
        """Handle /ask command"""
        user_id = update.effective_user.id
        t = self.context.translator.t

        if not context.args:
            await update.effective_message.reply_text(
                "❌ Vui lòng nhập câu hỏi\n\n"
                "Ví dụ: /ask Python là gì?"
            )
            return

        question = " ".join(context.args)

        # Show thinking message
        thinking_msg = await update.effective_message.reply_text(
            t('ai.thinking', user_id)
        )

        try:
            # Prepare messages for AI
            messages = [
                {
                    "role": "system",
                    "content": "Bạn là một trợ lý AI hữu ích. Trả lời bằng tiếng Việt."
                },
                {
                    "role": "user",
                    "content": question
                }
            ]

            # Route to AI provider
            response = await self.context.ai_router.chat(messages)

            # Edit thinking message with response
            await thinking_msg.edit_text(
                f"🤖 **AI Response:**\n\n{response}",
                parse_mode="Markdown"
            )

        except Exception as e:
            await thinking_msg.edit_text(
                f"{t('ai.error', user_id)}\n\nChi tiết: {str(e)}"
            )
