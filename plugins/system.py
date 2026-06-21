"""System Plugin - Core system commands"""
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from core.plugin import BasePlugin


class SystemPlugin(BasePlugin):
    """System commands plugin"""

    name = "system"
    description = "Core system commands"
    commands = ["start", "help", "menu", "id", "lang"]

    def register_handlers(self, app):
        """Register system command handlers"""
        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("menu", self.menu_command))
        app.add_handler(CommandHandler("id", self.id_command))
        app.add_handler(CommandHandler("lang", self.lang_command))

    async def start_command(self, update: Update, context: CallbackContext):
        """Handle /start command"""
        welcome_msg = self.context.translator.t('welcome', update.effective_user.id)
        help_title = self.context.translator.t('help.title', update.effective_user.id)

        message = f"{welcome_msg}\n\n{help_title}\n"
        message += "Gõ /help để xem danh sách lệnh\n"
        message += "Gõ /menu để sử dụng menu tương tác"

        await update.effective_message.reply_text(message)

    async def help_command(self, update: Update, context: CallbackContext):
        """Handle /help command"""
        user_id = update.effective_user.id
        t = self.context.translator.t

        commands = t('help.commands', user_id)

        message = f"📋 **{t('help.title', user_id)}**\n\n"
        message += f"{t('help.description', user_id)}\n\n"

        for cmd, desc in commands.items():
            message += f"/{cmd} - {desc}\n"

        await update.effective_message.reply_text(message)

    async def menu_command(self, update: Update, context: CallbackContext):
        """Handle /menu command"""
        keyboard = self.context.menu_manager.create_main_menu()

        await update.effective_message.reply_text(
            "📋 **Menu chính**\n\nChọn một mục:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

    async def id_command(self, update: Update, context: CallbackContext):
        """Handle /id command"""
        user = update.effective_user
        message = f"👤 **Thông tin của bạn:**\n\n"
        message += f"ID: `{user.id}`\n"
        message += f"Username: @{user.username}\n"
        message += f"Tên: {user.full_name}"

        await update.effective_message.reply_text(message, parse_mode="Markdown")

    async def lang_command(self, update: Update, context: CallbackContext):
        """Handle /lang command"""
        user_id = update.effective_user.id
        args = context.args

        if not args:
            current_lang = self.context.translator.get_user_language(user_id)
            available = self.context.translator.get_available_languages()

            message = f"🌐 Ngôn ngữ hiện tại: **{current_lang}**\n\n"
            message += "Ngôn ngữ có sẵn:\n"
            for lang in available:
                marker = "✓" if lang == current_lang else ""
                message += f"  {marker} {lang}\n"
            message += "\nĐể đổi ngôn ngữ: /lang <code>"

            await update.effective_message.reply_text(message, parse_mode="Markdown")
        else:
            new_lang = args[0].lower()
            if self.context.translator.has_language(new_lang):
                self.context.translator.set_user_language(user_id, new_lang)
                await update.effective_message.reply_text(
                    f"✅ Đã đổi ngôn ngữ sang: **{new_lang}**",
                    parse_mode="Markdown"
                )
            else:
                await update.effective_message.reply_text(
                    f"❌ Ngôn ngữ không hợp lệ: {new_lang}"
                )
