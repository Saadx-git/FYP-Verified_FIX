from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached: bool = False
    message: dict = field(default_factory=dict)

    @property
    def tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def load_api_key() -> str:
    """GROQ_API_KEY from the environment, falling back to a gitignored .env in the cwd."""
    key = os.environ.get("GROQ_API_KEY", "")
    env = Path(".env")
    if not key and env.is_file():
        for line in env.read_text().splitlines():
            if line.startswith("GROQ_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"'")
    return key


class GroqClient:
    """Minimal Groq (OpenAI-compatible) chat client: disk cache, 429 backoff, token accounting."""

    def __init__(self, api_key: str | None = None, cache_dir: str | None = ".verifix/cache",
                 max_retries: int = 5, transport=None) -> None:
        self.api_key = api_key if api_key is not None else load_api_key()
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.max_retries = max_retries
        self._transport = transport or self._http
        self.total_tokens = 0

    def chat(self, model: str, messages: list[dict], *, tools: list[dict] | None = None,
             temperature: float = 0.0, max_tokens: int = 2048, json_mode: bool = False,
             use_cache: bool = True, reasoning_effort: str | None = None) -> LLMResponse:
        body: dict = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if tools:
            body["tools"] = tools
        if reasoning_effort:
            body["reasoning_effort"] = reasoning_effort
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        cache_file = self._cache_file(body) if use_cache and temperature == 0 else None
        if cache_file and cache_file.is_file():
            data = json.loads(cache_file.read_text())
            return self._parse(data, cached=True)
        data = self._with_retries(body)
        if cache_file:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(data))
        resp = self._parse(data)
        self.total_tokens += resp.tokens
        return resp

    def _cache_file(self, body: dict) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / (hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() + ".json")

    def _with_retries(self, body: dict) -> dict:
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY is not set (export it or put it in a gitignored .env)")
        delay = 2.0
        for attempt in range(self.max_retries + 1):
            try:
                return self._transport(body)
            except urllib.error.HTTPError as e:
                if e.code not in (429, 500, 502, 503) or attempt == self.max_retries:
                    raise RuntimeError(f"Groq API error {e.code}: {e.read().decode()[:300]}") from e
                wait = float(e.headers.get("retry-after") or delay)
                time.sleep(min(wait, 60))
                delay *= 2
        raise RuntimeError("unreachable")

    def _http(self, body: dict) -> dict:
        req = urllib.request.Request(
            GROQ_URL, data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                     "User-Agent": "verifix/0.1 (+https://github.com/Saadx-git)"},
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())

    @staticmethod
    def _parse(data: dict, cached: bool = False) -> LLMResponse:
        msg = data["choices"][0]["message"]
        usage = data.get("usage", {})
        return LLMResponse(
            text=msg.get("content") or "", tool_calls=msg.get("tool_calls") or [],
            prompt_tokens=0 if cached else usage.get("prompt_tokens", 0),
            completion_tokens=0 if cached else usage.get("completion_tokens", 0), cached=cached, message=msg,
        )
