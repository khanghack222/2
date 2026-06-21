"""
OpenRouter Provider - Free AI models via OpenRouter
"""
import aiohttp
from typing import List, Dict
from ai.router import BaseProvider


class OpenRouterProvider(BaseProvider):
    """Provider for OpenRouter API"""

    def __init__(self, api_key: str = ""):
        super().__init__(
            name="OpenRouter",
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            model="anthropic/claude-3-haiku"
        )

    async def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """Send chat request to OpenRouter"""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/telegram-bot",
            "X-Title": "Telegram Bot"
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2000),
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"HTTP {response.status}: {error_text}")

                data = await response.json()

                if "choices" not in data or not data["choices"]:
                    raise Exception("No response from OpenRouter")

                return data["choices"][0]["message"]["content"]
