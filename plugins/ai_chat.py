"""AI Chat Plugin - Ask AI questions"""
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, CallbackContext, filters
from core.plugin import BasePlugin


class AIChatPlugin(BasePlugin):
    """AI chat plugin"""

    name = "ai_chat"
    description = "AI chatbot commands"
    commands = ["ask"]

    def __init__(self, context):
        super().__init__(context)
        self._conversation_history = {}  # {user_id: [(role, content), ...]}

    def register_handlers(self, app):
        """Register AI chat command handlers"""
        app.add_handler(CommandHandler("ask", self.ask_command))
        # Handle replies to bot messages
        app.add_handler(MessageHandler(
            filters.TEXT & filters.REPLY & ~filters.COMMAND,
            self.handle_reply
        ))

    async def ask_command(self, update: Update, context: CallbackContext):
        """Handle /ask command"""
        user_id = update.effective_user.id
        t = self.context.translator.t

        if not context.args:
            await update.effective_message.reply_text(
                "❌ Vui lòng nhập câu hỏi\n\n"
                "Ví dụ: /ask Python là gì?\n\n"
                "💡 **Mẹo:** Bạn cũng có thể reply trực tiếp vào tin nhắn của bot để tiếp tục cuộc trò chuyện!"
            )
            return

        question = " ".join(context.args)
        await self._process_ai_request(update, question, user_id)

    async def handle_reply(self, update: Update, context: CallbackContext):
        """Handle replies to bot messages"""
        # Check if this is a reply to a bot message
        if not update.message.reply_to_message:
            return

        replied_msg = update.message.reply_to_message
        bot_username = context.bot.username

        # Check if replying to bot's message
        if replied_msg.from_user.username != bot_username:
            return

        user_id = update.effective_user.id
        question = update.message.text

        await self._process_ai_request(update, question, user_id)

    async def _process_ai_request(self, update: Update, question: str, user_id: int):
        """Process AI request with conversation history"""
        t = self.context.translator.t

        # Show thinking message
        thinking_msg = await update.effective_message.reply_text(
            t('ai.thinking', user_id)
        )

        try:
            # Get or initialize conversation history
            if user_id not in self._conversation_history:
                self._conversation_history[user_id] = []

            history = self._conversation_history[user_id]

            # Add user's question to history
            history.append(("user", question))

            # Build messages array with history (last 10 exchanges to avoid token limit)
            messages = [
                {
                    "role": "system",
                    "content": "Bạn là một trợ lý AI hữu ích. Trả lời bằng tiếng Việt. Hãy nhớ ngữ cảnh cuộc trò chuyện trước đó."
                }
            ]

            # Add conversation history (last 20 messages = 10 exchanges)
            for role, content in history[-20:]:
                messages.append({
                    "role": role,
                    "content": content
                })

            # Route to AI provider
            response = await self.context.ai_router.chat(messages)

            # Add bot's response to history
            history.append(("assistant", response))

            # Keep history manageable (max 40 messages = 20 exchanges)
            if len(history) > 40:
                self._conversation_history[user_id] = history[-40:]

            # Edit thinking message with response
            await thinking_msg.edit_text(
                f"🤖 {response}",
                parse_mode="Markdown"
            )

        except Exception as e:
            # Remove the failed question from history
            if user_id in self._conversation_history and self._conversation_history[user_id]:
                if self._conversation_history[user_id][-1][0] == "user":
                    self._conversation_history[user_id].pop()

            await thinking_msg.edit_text(
                f"{t('ai.error', user_id)}\n\nChi tiết: {str(e)}"
            )

    def clear_history(self, user_id: int):
        """Clear conversation history for a user"""
        if user_id in self._conversation_history:
            del self._conversation_history[user_id]
