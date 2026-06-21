"""Reminder Plugin - Reminder management commands"""
import asyncio
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from core.plugin import BasePlugin


class ReminderPlugin(BasePlugin):
    """Reminder commands plugin"""

    name = "reminder"
    description = "Reminder management commands"
    commands = ["remind", "reminders", "delremind"]

    def __init__(self, context):
        super().__init__(context)
        self._reminder_tasks = {}

    def register_handlers(self, app):
        """Register reminder command handlers"""
        app.add_handler(CommandHandler("remind", self.remind_command))
        app.add_handler(CommandHandler("reminders", self.list_command))
        app.add_handler(CommandHandler("delremind", self.delete_command))

    async def remind_command(self, update: Update, context: CallbackContext):
        """Handle /remind command"""
        user_id = update.effective_user.id
        t = self.context.translator.t

        if len(context.args) < 2:
            await update.effective_message.reply_text(
                "❌ Cách dùng: /remind <phút> <nội dung>\n\n"
                "Ví dụ: /remind 30 Họp nhóm lúc 3h"
            )
            return

        try:
            minutes = int(context.args[0])
            content = " ".join(context.args[1:])

            if minutes < 1 or minutes > 1440:  # Max 24 hours
                await update.effective_message.reply_text(
                    "❌ Thời gian phải từ 1 đến 1440 phút"
                )
                return

            # Calculate reminder time
            remind_at = datetime.now() + timedelta(minutes=minutes)

            # Save to database
            reminder_id = await self.context.reminder_service.create_reminder(
                user_id=user_id,
                content=content,
                remind_at=remind_at
            )

            # Schedule async task
            task = asyncio.create_task(
                self._schedule_reminder(
                    reminder_id,
                    user_id,
                    minutes * 60,  # Convert to seconds
                    content
                )
            )
            self._reminder_tasks[reminder_id] = task

            await update.effective_message.reply_text(
                t('reminder.created', user_id, time=remind_at.strftime("%H:%M %d/%m/%Y"))
            )

        except ValueError:
            await update.effective_message.reply_text(
                "❌ Thời gian phải là số phút"
            )

    async def list_command(self, update: Update, context: CallbackContext):
        """Handle /reminders command"""
        user_id = update.effective_user.id
        t = self.context.translator.t

        reminders = await self.context.reminder_service.get_user_reminders(user_id)

        if not reminders:
            await update.effective_message.reply_text(
                t('reminder.list_empty', user_id)
            )
            return

        message = "📋 **Danh sách nhắc nhở:**\n\n"

        for reminder in reminders:
            remind_at = reminder['remind_at']
            time_str = remind_at.strftime("%H:%M %d/%m")
            message += f"#{reminder['id']} - {time_str}\n"
            message += f"  📝 {reminder['content']}\n\n"

        await update.effective_message.reply_text(message, parse_mode="Markdown")

    async def delete_command(self, update: Update, context: CallbackContext):
        """Handle /delremind command"""
        user_id = update.effective_user.id
        t = self.context.translator.t

        if not context.args:
            await update.effective_message.reply_text(
                "❌ Cách dùng: /delremind <id>"
            )
            return

        try:
            reminder_id = int(context.args[0])

            # Cancel scheduled task
            if reminder_id in self._reminder_tasks:
                self._reminder_tasks[reminder_id].cancel()
                del self._reminder_tasks[reminder_id]

            # Delete from database
            deleted = await self.context.reminder_service.delete_reminder(
                reminder_id,
                user_id
            )

            if deleted:
                await update.effective_message.reply_text(
                    t('reminder.deleted', user_id, id=reminder_id)
                )
            else:
                await update.effective_message.reply_text(
                    t('reminder.not_found', user_id, id=reminder_id)
                )

        except ValueError:
            await update.effective_message.reply_text(
                "❌ ID phải là số"
            )

    async def _schedule_reminder(
        self,
        reminder_id: int,
        user_id: int,
        delay_seconds: int,
        content: str
    ):
        """Schedule and send reminder after delay"""
        try:
            await asyncio.sleep(delay_seconds)

            # Send reminder message
            await self.context.bot.send_message(
                chat_id=user_id,
                text=f"⏰ **Nhắc nhở:**\n\n{content}",
                parse_mode="Markdown"
            )

            # Delete from database
            await self.context.reminder_service.delete_reminder(
                reminder_id,
                user_id
            )

            # Clean up task reference
            if reminder_id in self._reminder_tasks:
                del self._reminder_tasks[reminder_id]

        except asyncio.CancelledError:
            # Task was cancelled, ignore
            pass
        except Exception as e:
            print(f"Reminder error: {e}")
