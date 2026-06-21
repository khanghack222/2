"""Stock Plugin - Stock price commands"""
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from core.plugin import BasePlugin


class StockPlugin(BasePlugin):
    """Stock price commands plugin"""

    name = "stock"
    description = "Stock price commands"
    commands = ["stock"]

    def register_handlers(self, app):
        """Register stock command handlers"""
        app.add_handler(CommandHandler("stock", self.stock_command))

    async def stock_command(self, update: Update, context: CallbackContext):
        """Handle /stock command"""
        user_id = update.effective_user.id

        if not context.args:
            await update.effective_message.reply_text(
                "❌ Cách dùng: /stock <mã>\n\n"
                "Ví dụ: /stock AAPL\n"
                "Ví dụ: /stock MSFT"
            )
            return

        symbol = context.args[0].upper()

        try:
            # Check cache first
            cache_key = f"stock:{symbol}"
            cached = self.context.cache.get(cache_key)

            if cached:
                await update.effective_message.reply_text(cached, parse_mode="Markdown")
                return

            # Fetch stock data
            stock_data = await self._get_stock_price(symbol)

            if not stock_data:
                await update.effective_message.reply_text(
                    f"❌ Không tìm thấy cổ phiếu: {symbol}"
                )
                return

            price = stock_data['price']
            change = stock_data['change']
            change_percent = stock_data['change_percent']
            emoji = "📈" if change >= 0 else "📉"

            message = f"📊 **{stock_data['name']}** ({symbol})\n\n"
            message += f"💰 Giá: ${price:.2f}\n"
            message += f"{emoji} Thay đổi: {change:+.2f} ({change_percent:+.2f}%)\n\n"

            if 'volume' in stock_data:
                message += f"📦 Khối lượng: {stock_data['volume']:,}\n"

            if 'market_cap' in stock_data:
                message += f"🏢 Vốn hóa: ${stock_data['market_cap']:,}"

            # Cache for 2 minutes
            self.context.cache.set(cache_key, message, ttl=120)

            await update.effective_message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            await update.effective_message.reply_text(
                f"❌ Lỗi khi lấy giá cổ phiếu: {symbol}"
            )
            print(f"Stock error: {e}")

    async def _get_stock_price(self, symbol: str) -> dict:
        """Fetch stock price using Yahoo Finance"""
        try:
            import yfinance as yf

            # Get stock info
            stock = yf.Ticker(symbol)
            info = stock.info

            if not info or 'regularMarketPrice' not in info:
                return None

            price = info.get('regularMarketPrice', 0)
            prev_close = info.get('regularMarketPreviousClose', price)
            change = price - prev_close
            change_percent = (change / prev_close * 100) if prev_close else 0

            return {
                'name': info.get('shortName', symbol),
                'symbol': symbol,
                'price': price,
                'change': change,
                'change_percent': change_percent,
                'volume': info.get('regularMarketVolume', 0),
                'market_cap': info.get('marketCap', 0)
            }

        except Exception as e:
            print(f"yfinance error: {e}")
            return None
