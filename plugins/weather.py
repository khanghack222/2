"""Weather Plugin - Weather information commands"""
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from core.plugin import BasePlugin


class WeatherPlugin(BasePlugin):
    """Weather commands plugin"""

    name = "weather"
    description = "Weather information commands"
    commands = ["weather"]

    def register_handlers(self, app):
        """Register weather command handlers"""
        app.add_handler(CommandHandler("weather", self.weather_command))

    async def weather_command(self, update: Update, context: CallbackContext):
        """Handle /weather command"""
        user_id = update.effective_user.id
        t = self.context.translator.t

        if not context.args:
            await update.effective_message.reply_text(
                "❌ Vui lòng nhập tên thành phố\n\n"
                "Ví dụ: /weather Hanoi"
            )
            return

        city = " ".join(context.args)

        try:
            # Check cache first
            cache_key = f"weather:{city.lower()}"
            cached = self.context.cache.get(cache_key)

            if cached:
                await update.effective_message.reply_text(cached, parse_mode="Markdown")
                return

            # Call weather API
            weather_data = await self.get_weather(city)

            if not weather_data:
                await update.effective_message.reply_text(
                    t('weather.city_not_found', user_id, city=city)
                )
                return

            # Format response
            current = weather_data['current']
            message = t(
                'weather.result',
                user_id,
                city=city,
                temp=current['temperature_2m'],
                humidity=current['relative_humidity_2m'],
                wind=current['wind_speed_10m']
            )

            # Cache for 5 minutes
            self.context.cache.set(cache_key, message, ttl=300)

            await update.effective_message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            await update.effective_message.reply_text(
                t('weather.error', user_id)
            )
            print(f"Weather error: {e}")

    async def get_weather(self, city: str) -> dict:
        """Fetch weather data from API"""
        # First, geocode the city
        geocode_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"

        try:
            geocode_data = await self.context.http_client.get(geocode_url)

            if not geocode_data.get('results'):
                return None

            location = geocode_data['results'][0]
            lat = location['latitude']
            lon = location['longitude']

            # Get weather data
            weather_url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}&"
                f"current=temperature_2m,relative_humidity_2m,wind_speed_10m"
            )

            weather_data = await self.context.http_client.get(weather_url)
            return weather_data

        except Exception:
            return None
