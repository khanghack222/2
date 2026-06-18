"""ai_chat.py — AI Chatbot using free LLM APIs."""
import os
import logging
import json
import asyncio
import urllib.request
import urllib.parse
import urllib.error

logger = logging.getLogger(__name__)

# Support multiple providers via env vars
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")  # Free LLM API
AI_MODEL = os.environ.get("AI_MODEL", "llama-3.3-70b-versatile")
SYSTEM_PROMPT = (
    "Bạn là trợ lý AI thân thiện, trả lời bằng tiếng Việt. "
    "Ngắn gọn, rõ ràng, hữu ích."
)


async def ask_ai(question: str) -> str:
    """Send question to the best available LLM provider."""
    if GROQ_API_KEY:
        return await _ask_groq(question)
    elif OPENAI_API_KEY:
        return await _ask_openai(question)
    else:
        return (
            "❌ Chưa cấu hình AI API key.\n\n"
            "Set env var:\n"
            "• `GROQ_API_KEY` (miễn phí): https://console.groq.com\n"
            "• `OPENAI_API_KEY` (trả phí): https://platform.openai.com"
        )


async def _ask_groq(question: str) -> str:
    """Use Groq free LLM API."""
    try:
        body = json.dumps({
            "model": AI_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            "max_tokens": 1024,
            "temperature": 0.7,
        }).encode()

        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
        )

        def _call():
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())

        data = await asyncio.to_thread(_call)
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return f"❌ Lỗi AI: {e}"


async def _ask_openai(question: str) -> str:
    """Use OpenAI API."""
    try:
        body = json.dumps({
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            "max_tokens": 1024,
        }).encode()

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
        )

        def _call():
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())

        data = await asyncio.to_thread(_call)
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return f"❌ Lỗi AI: {e}"
