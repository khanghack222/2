"""Password Plugin - Password management commands"""
import secrets
import string
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from core.plugin import BasePlugin


class PasswordPlugin(BasePlugin):
    """Password management commands plugin"""

    name = "password"
    description = "Password management commands"
    commands = ["password", "genpass", "mypasswords", "delpassword"]

    def register_handlers(self, app):
        """Register password command handlers"""
        app.add_handler(CommandHandler("password", self.password_command))
        app.add_handler(CommandHandler("genpass", self.genpass_command))
        app.add_handler(CommandHandler("mypasswords", self.list_command))
        app.add_handler(CommandHandler("delpassword", self.delete_command))

    async def password_command(self, update: Update, context: CallbackContext):
        """Handle /password command - save a password"""
        user_id = update.effective_user.id
        t = self.context.translator.t

        if len(context.args) < 2:
            await update.effective_message.reply_text(
                "❌ Cách dùng: /password <nhãn> <mật khẩu>\n\n"
                "Ví dụ: /password gmail mypassword123\n\n"
                "Hoặc dùng /genpass để tạo mật khẩu ngẫu nhiên"
            )
            return

        label = context.args[0]
        password = " ".join(context.args[1:])

        try:
            # Save password (encrypted)
            password_id = await self.context.password_service.save_password(
                user_id=user_id,
                label=label,
                password=password
            )

            await update.effective_message.reply_text(
                t('password.created', user_id, label=label)
            )

        except Exception as e:
            await update.effective_message.reply_text(
                t('error.generic', user_id)
            )
            print(f"Password save error: {e}")

    async def genpass_command(self, update: Update, context: CallbackContext):
        """Handle /genpass command - generate random password"""
        user_id = update.effective_user.id

        # Default length 16, or use provided length
        length = 16
        label = None

        if context.args:
            try:
                length = int(context.args[0])
                if length < 8 or length > 64:
                    length = 16
            except ValueError:
                pass

            if len(context.args) > 1:
                label = context.args[1]

        # Generate password
        alphabet = string.ascii_letters + string.digits + string.punctuation
        password = ''.join(secrets.choice(alphabet) for _ in range(length))

        message = f"🔐 **Mật khẩu ngẫu nhiên:**\n\n"
        message += f"```\n{password}\n```\n\n"
        message += f"Độ dài: {length} ký tự"

        # Save if label provided
        if label:
            try:
                await self.context.password_service.save_password(
                    user_id=user_id,
                    label=label,
                    password=password
                )
                message += f"\n\n✅ Đã lưu với nhãn: **{label}**"
            except Exception as e:
                message += f"\n\n⚠️ Không thể lưu: {str(e)}"

        await update.effective_message.reply_text(message, parse_mode="Markdown")

    async def list_command(self, update: Update, context: CallbackContext):
        """Handle /mypasswords command - list saved passwords"""
        user_id = update.effective_user.id
        t = self.context.translator.t

        try:
            passwords = await self.context.password_service.get_passwords(user_id)

            if not passwords:
                await update.effective_message.reply_text(
                    t('password.list_empty', user_id)
                )
                return

            message = "🔐 **Mật khẩu đã lưu:**\n\n"

            for pwd in passwords:
                message += f"**#{pwd['id']}** - {pwd['label']}\n"
                message += f"  🔑 `{pwd['password']}`\n\n"

            message += "💡 Dùng /delpassword <id> để xóa"

            await update.effective_message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            await update.effective_message.reply_text(
                t('error.generic', user_id)
            )
            print(f"Password list error: {e}")

    async def delete_command(self, update: Update, context: CallbackContext):
        """Handle /delpassword command - delete a password"""
        user_id = update.effective_user.id
        t = self.context.translator.t

        if not context.args:
            await update.effective_message.reply_text(
                "❌ Cách dùng: /delpassword <id>\n\n"
                "Ví dụ: /delpassword 1"
            )
            return

        try:
            password_id = int(context.args[0])

            deleted = await self.context.password_service.delete_password(
                password_id,
                user_id
            )

            if deleted:
                await update.effective_message.reply_text(
                    t('password.deleted', user_id, id=password_id)
                )
            else:
                await update.effective_message.reply_text(
                    t('password.not_found', user_id, id=password_id)
                )

        except ValueError:
            await update.effective_message.reply_text(
                "❌ ID phải là số"
            )
        except Exception as e:
            await update.effective_message.reply_text(
                t('error.generic', user_id)
            )
            print(f"Password delete error: {e}")
