"""
LLM provider abstraction for generation. Default is Groq's free tier
(llama-3.3-70b-versatile) — fast, no cost, no credit card required to sign
up at https://console.groq.com/keys. Swap LLM_PROVIDER in .env to "gemini"
(also free-tier), or "openai"/"anthropic" if you add a paid key.

Everything downstream (generation/answer.py) only calls .stream(messages),
so it doesn't care which provider is behind it.
"""
from __future__ import annotations

from collections.abc import Iterator

import config


class LLMClient:
    def stream(self, messages: list[dict], temperature: float = 0.0) -> Iterator[str]:
        """Yields text chunks as they arrive."""
        raise NotImplementedError

    def complete(self, messages: list[dict], temperature: float = 0.0) -> str:
        return "".join(self.stream(messages, temperature=temperature))


class GroqClient(LLMClient):
    def __init__(self):
        from groq import Groq

        if not config.GROQ_API_KEY:
            raise RuntimeError(
                "GROQ_API_KEY not set in .env — get a free key at "
                "https://console.groq.com/keys (no card required)"
            )
        self.client = Groq(api_key=config.GROQ_API_KEY)
        self.model = config.GROQ_MODEL

    def stream(self, messages, temperature: float = 0.0) -> Iterator[str]:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            stream=True,
        )
        for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


class GeminiClient(LLMClient):
    def __init__(self):
        import google.generativeai as genai

        if not config.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY not set in .env — get a free key at "
                "https://aistudio.google.com/apikey (no card required)"
            )
        genai.configure(api_key=config.GEMINI_API_KEY)
        self.model = genai.GenerativeModel(config.GEMINI_MODEL)

    def stream(self, messages, temperature: float = 0.0) -> Iterator[str]:
        # Gemini wants a single prompt string rather than an OpenAI-style
        # message list; flatten it, keeping the system prompt on top.
        prompt = "\n\n".join(m["content"] for m in messages)
        response = self.model.generate_content(
            prompt,
            generation_config={"temperature": temperature},
            stream=True,
        )
        for chunk in response:
            if chunk.text:
                yield chunk.text


class OpenAIClient(LLMClient):
    def __init__(self):
        from openai import OpenAI

        if not config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not set in .env")
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)
        self.model = config.OPENAI_MODEL

    def stream(self, messages, temperature: float = 0.0) -> Iterator[str]:
        response = self.client.chat.completions.create(
            model=self.model, messages=messages, temperature=temperature, stream=True
        )
        for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


class AnthropicClient(LLMClient):
    def __init__(self):
        import anthropic

        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY not set in .env")
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.model = config.ANTHROPIC_MODEL

    def stream(self, messages, temperature: float = 0.0) -> Iterator[str]:
        system = next((m["content"] for m in messages if m["role"] == "system"), None)
        turns = [m for m in messages if m["role"] != "system"]
        with self.client.messages.stream(
            model=self.model,
            system=system,
            messages=turns,
            temperature=temperature,
            max_tokens=1024,
        ) as stream:
            yield from stream.text_stream


def get_llm_client() -> LLMClient:
    provider = config.LLM_PROVIDER
    if provider == "groq":
        return GroqClient()
    if provider == "gemini":
        return GeminiClient()
    if provider == "openai":
        return OpenAIClient()
    if provider == "anthropic":
        return AnthropicClient()
    raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}")
