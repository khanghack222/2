"""
OpenAI Provider - GPT models
"""
import aiohttp
from typing import List, Dict
from ai.router import BaseProvider


class OpenAIProvider(BaseProvider):
    """Provider for OpenAI API"""

    def __init__(self, api_key: str, model: str = "gpt-3.5-turbo"):
        super().__init__(
            name="OpenAI",
            api_key=api_key,
            base_url="https://api.openai.com/v1",
            model=model
        )

    async def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """Send chat request to OpenAI"""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
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
                    raise Exception("No response from OpenAI")

                return data["choices"][0]["message"]["content"]
