"""
Middleware implementations for the pipeline
"""
import time
import asyncio
from typing import Callable, Any, Dict
from collections import defaultdict
from telegram import Update
from telegram.ext import CallbackContext
from core.middleware import Middleware
from core.context import AppContext


class RateLimitMiddleware(Middleware):
    """Rate limiting middleware"""

    def __init__(self, context: AppContext):
        self.context = context
        self._requests: Dict[int, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def handle(
        self,
        update: Update,
        context: CallbackContext,
        next_handler: Callable
    ) -> Any:
        """Check rate limit before proceeding"""
        user_id = update.effective_user.id

        async with self._lock:
            now = time.time()
            window = self.context.config.rate_limit_window
            max_requests = self.context.config.rate_limit_max_requests

            # Remove old requests
            self._requests[user_id] = [
                t for t in self._requests[user_id]
                if now - t < window
            ]

            # Check limit
            if len(self._requests[user_id]) >= max_requests:
                await update.effective_message.reply_text(
                    f"⏳ Bạn đang gửi quá nhiều yêu cầu. Vui lòng thử lại sau {int(window)} giây."
                )
                return

            # Record request
            self._requests[user_id].append(now)

        return await next_handler(update, context)


class ErrorHandlingMiddleware(Middleware):
    """Error handling middleware"""

    def __init__(self, context: AppContext):
        self.context = context

    async def handle(
        self,
        update: Update,
        context: CallbackContext,
        next_handler: Callable
    ) -> Any:
        """Catch and handle errors"""
        try:
            return await next_handler(update, context)
        except Exception as e:
            error_msg = f"❌ Lỗi: {str(e)}"
            await update.effective_message.reply_text(error_msg)

            # Log error
            print(f"Error in handler: {e}")
            import traceback
            traceback.print_exc()


class LoggingMiddleware(Middleware):
    """Request logging middleware"""

    def __init__(self, context: AppContext):
        self.context = context

    async def handle(
        self,
        update: Update,
        context: CallbackContext,
        next_handler: Callable
    ) -> Any:
        """Log request and track metrics"""
        start_time = time.time()

        user_id = update.effective_user.id
        username = update.effective_user.username or "unknown"
        command = ""

        if update.effective_message and update.effective_message.text:
            text = update.effective_message.text
            if text.startswith('/'):
                command = text.split()[0].split('@')[0]

        # Execute handler
        success = True
        try:
            result = await next_handler(update, context)
            return result
        except Exception as e:
            success = False
            raise
        finally:
            duration_ms = (time.time() - start_time) * 1000

            # Log to database
            try:
                await self.context.repos.stats.log_usage(
                    user_id=user_id,
                    command=command or "unknown",
                    success=success,
                    duration_ms=int(duration_ms)
                )
            except Exception as log_error:
                print(f"Failed to log usage: {log_error}")
