"""
Groq Provider - Fast inference for open models
"""
import aiohttp
from typing import List, Dict
from ai.router import BaseProvider


class GroqProvider(BaseProvider):
    """Provider for Groq API"""

    def __init__(self, api_key: str):
        super().__init__(
            name="Groq",
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
            model="mixtral-8x7b-32768"
        )

    async def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """Send chat request to Groq"""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 4000),
            "stream": False
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
                    raise Exception("No response from Groq")

                return data["choices"][0]["message"]["content"]
