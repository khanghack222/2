"""
Middleware Pipeline - Request Processing Chain
Pattern: Chain of responsibility for cross-cutting concerns
"""
from abc import ABC, abstractmethod
from typing import Callable, Any
from telegram import Update
from telegram.ext import CallbackContext


class Middleware(ABC):
    """Base class for all middleware"""

    @abstractmethod
    async def handle(
        self,
        update: Update,
        context: CallbackContext,
        next_handler: Callable[[Update, CallbackContext], Any]
    ) -> Any:
        """
        Process the request and call next handler.

        Args:
            update: Telegram update object
            context: Telegram callback context
            next_handler: Next handler in the chain

        Returns:
            Result from the handler chain
        """
        pass


class MiddlewarePipeline:
    """
    Manages a chain of middleware for processing requests.
    Similar to Express.js middleware or Django middleware.
    """

    def __init__(self):
        self._middlewares: list[Middleware] = []

    def use(self, middleware: Middleware) -> "MiddlewarePipeline":
        """
        Add middleware to the pipeline.

        Args:
            middleware: Middleware instance to add

        Returns:
            Self for chaining
        """
        self._middlewares.append(middleware)
        return self

    async def execute(
        self,
        update: Update,
        context: CallbackContext,
        handler: Callable[[Update, CallbackContext], Any]
    ) -> Any:
        """
        Execute the middleware chain with the final handler.

        Args:
            update: Telegram update object
            context: Telegram callback context
            handler: Final handler to execute after middleware

        Returns:
            Result from the handler chain
        """

        async def execute_chain(index: int) -> Any:
            if index >= len(self._middlewares):
                # End of middleware chain, execute final handler
                return await handler(update, context)

            # Execute current middleware with next handler
            middleware = self._middlewares[index]
            return await middleware.handle(
                update,
                context,
                lambda u, c: execute_chain(index + 1)
            )

        return await execute_chain(0)

    def wrap_handler(
        self,
        handler: Callable[[Update, CallbackContext], Any]
    ) -> Callable[[Update, CallbackContext], Any]:
        """
        Wrap a handler with the middleware pipeline.

        Args:
            handler: Handler to wrap

        Returns:
            Wrapped handler function
        """

        async def wrapped(update: Update, context: CallbackContext) -> Any:
            return await self.execute(update, context, handler)

        return wrapped
