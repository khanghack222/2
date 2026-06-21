"""Crypto Plugin - Cryptocurrency price commands"""
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from core.plugin import BasePlugin


class CryptoPlugin(BasePlugin):
    """Cryptocurrency commands plugin"""

    name = "crypto"
    description = "Cryptocurrency price commands"
    commands = ["crypto", "price"]

    def register_handlers(self, app):
        """Register crypto command handlers"""
        app.add_handler(CommandHandler("crypto", self.crypto_command))
        app.add_handler(CommandHandler("price", self.price_command))

    async def crypto_command(self, update: Update, context: CallbackContext):
        """Handle /crypto command - show top cryptocurrencies"""
        user_id = update.effective_user.id
        t = self.context.translator.t

        try:
            # Check cache first
            cache_key = "crypto:top"
            cached = self.context.cache.get(cache_key)

            if cached:
                await update.effective_message.reply_text(cached, parse_mode="Markdown")
                return

            # Fetch from CoinGecko API
            coins = await self._get_top_coins()

            if not coins:
                await update.effective_message.reply_text(
                    t('crypto.error', user_id)
                )
                return

            # Format message
            message = "💰 **Top Cryptocurrency Prices:**\n\n"

            for coin in coins[:10]:
                symbol = coin['symbol'].upper()
                price = coin['current_price']
                change_24h = coin['price_change_percentage_24h']
                emoji = "📈" if change_24h >= 0 else "📉"

                message += f"**{coin['name']}** ({symbol})\n"
                message += f"  💵 ${price:,.2f}\n"
                message += f"  {emoji} {change_24h:+.2f}% (24h)\n\n"

            # Cache for 5 minutes
            self.context.cache.set(cache_key, message, ttl=300)

            await update.effective_message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            await update.effective_message.reply_text(
                t('crypto.error', user_id)
            )
            print(f"Crypto error: {e}")

    async def price_command(self, update: Update, context: CallbackContext):
        """Handle /price command - get specific coin price"""
        user_id = update.effective_user.id
        t = self.context.translator.t

        if not context.args:
            await update.effective_message.reply_text(
                "❌ Cách dùng: /price <coin>\n\n"
                "Ví dụ: /price bitcoin"
            )
            return

        coin_name = context.args[0].lower()

        try:
            # Check cache
            cache_key = f"crypto:{coin_name}"
            cached = self.context.cache.get(cache_key)

            if cached:
                await update.effective_message.reply_text(cached, parse_mode="Markdown")
                return

            # Fetch coin data
            coin_data = await self._get_coin_price(coin_name)

            if not coin_data:
                await update.effective_message.reply_text(
                    f"❌ Không tìm thấy coin: {coin_name}"
                )
                return

            symbol = coin_data['symbol'].upper()
            price = coin_data['current_price']
            change_24h = coin_data['price_change_percentage_24h']
            emoji = "📈" if change_24h >= 0 else "📉"

            message = t(
                'crypto.price',
                user_id,
                coin=coin_data['name'],
                price=f"{price:,.2f}",
                change=f"{change_24h:+.2f}"
            )

            message += f"\n\n{emoji} **Chi tiết:**\n"
            message += f"Symbol: {symbol}\n"
            message += f"Market Cap: ${coin_data.get('market_cap', 0):,.0f}\n"
            message += f"24h Volume: ${coin_data.get('total_volume', 0):,.0f}"

            # Cache for 2 minutes
            self.context.cache.set(cache_key, message, ttl=120)

            await update.effective_message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            await update.effective_message.reply_text(
                t('crypto.error', user_id)
            )
            print(f"Price error: {e}")

    async def _get_top_coins(self) -> list:
        """Fetch top cryptocurrencies from CoinGecko"""
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 10,
            "page": 1,
            "sparkline": False
        }

        try:
            coins = await self.context.http_client.get(url, params=params)
            return coins if isinstance(coins, list) else []
        except Exception:
            return []

    async def _get_coin_price(self, coin_name: str) -> dict:
        """Fetch specific coin price from CoinGecko"""
        url = f"https://api.coingecko.com/api/v3/coins/{coin_name}"
        params = {
            "localization": False,
            "tickers": False,
            "market_data": True,
            "community_data": False,
            "developer_data": False
        }

        try:
            data = await self.context.http_client.get(url, params=params)

            if not data or 'market_data' not in data:
                return None

            market_data = data['market_data']

            return {
                'name': data['name'],
                'symbol': data['symbol'],
                'current_price': market_data['current_price']['usd'],
                'price_change_percentage_24h': market_data['price_change_percentage_24h'],
                'market_cap': market_data['market_cap']['usd'],
                'total_volume': market_data['total_volume']['usd']
            }

        except Exception:
            return None
