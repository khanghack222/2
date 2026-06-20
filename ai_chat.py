"""ai_chat.py — AI Chatbot using free LLM APIs."""
import os
import logging
import json
import asyncio
import urllib.request
import urllib.parse
import urllib.error

logger = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
AI_MODEL = os.environ.get("AI_MODEL", "llama-3.3-70b-versatile")

# 9Router on Render — OpenCode Free (miễn phí không giới hạn)
ROUTER_API_KEY = os.environ.get(
    "ROUTER_API_KEY",
    "sk-e4eeda3c27c1138d-t2fk64-45c4a4bc",
)
ROUTER_BASE_URL = os.environ.get(
    "ROUTER_BASE_URL",
    "https://ninerouter-z20n.onrender.com/v1",
)
ROUTER_MODEL = os.environ.get(
    "ROUTER_MODEL",
    "mmf/mimo-auto",
)

SYSTEM_PROMPT = (
    "Bạn là trợ lý AI thân thiện, trả lời bằng tiếng Việt. "
    "Ngắn gọn, rõ ràng, hữu ích."
)


async def ask_ai(question: str) -> str:
    """Send question to the best available LLM provider.

    Priority: 9Router (OpenCode Free) → Groq → OpenAI
    """
    # 1. 9Router / OpenCode Free (miễn phí) — luôn thử trước
    if ROUTER_BASE_URL:
        return await _ask_router(question)
    # 2. Groq (miễn phí)
    elif GROQ_API_KEY:
        return await _ask_groq(question)
    # 3. OpenAI (trả phí)
    elif OPENAI_API_KEY:
        return await _ask_openai(question)
    else:
        return (
            "❌ Chưa cấu hình AI API key.\n\n"
            "Set env var:\n"
            "• `ROUTER_API_KEY` (miễn phí): 9Router + OpenCode Free\n"
            "• `GROQ_API_KEY` (miễn phí): https://console.groq.com\n"
            "• `OPENAI_API_KEY` (trả phí): https://platform.openai.com"
        )


async def _ask_router(question: str) -> str:
    """Use 9Router (OpenCode Free / Kiro / any model)."""
    try:
        headers = {"Content-Type": "application/json"}
        if ROUTER_API_KEY:
            headers["Authorization"] = f"Bearer {ROUTER_API_KEY}"

        body = json.dumps({
            "model": ROUTER_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            "max_tokens": 1024,
            "temperature": 0.7,
        }).encode()

        req = urllib.request.Request(
            f"{ROUTER_BASE_URL}/chat/completions",
            data=body,
            headers=headers,
        )

        def _call():
            with urllib.request.urlopen(req, timeout=60) as resp:
                text = resp.read().decode()
                # SSE: parse first data: line from streaming response
                data_line = None
                for line in text.splitlines():
                    line = line.strip()
                    if line.startswith("data: ") and line != "data: [DONE]":
                        data_line = line[6:]
                if data_line:
                    return json.loads(data_line)
                return json.loads(text)

        data = await asyncio.to_thread(_call)
        return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        logger.error(f"Router HTTP error {e.code}: {e}")
        # Fallback: nếu 401 (key ko đúng), thử Groq
        if e.code == 401 and GROQ_API_KEY:
            return await _ask_groq(question)
        return f"❌ Lỗi AI (9Router): HTTP {e.code}"
    except Exception as e:
        logger.error(f"Router API error: {e}")
        return f"❌ Lỗi AI (9Router): {e}"


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
                text = resp.read().decode()
                # SSE: parse first data: line from streaming response
                data_line = None
                for line in text.splitlines():
                    line = line.strip()
                    if line.startswith("data: ") and line != "data: [DONE]":
                        data_line = line[6:]
                if data_line:
                    return json.loads(data_line)
                return json.loads(text)

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
                text = resp.read().decode()
                # SSE: parse first data: line from streaming response
                data_line = None
                for line in text.splitlines():
                    line = line.strip()
                    if line.startswith("data: ") and line != "data: [DONE]":
                        data_line = line[6:]
                if data_line:
                    return json.loads(data_line)
                return json.loads(text)

        data = await asyncio.to_thread(_call)
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return f"❌ Lỗi AI: {e}"
