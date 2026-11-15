"""One small interface to the LLM providers learners use: Claude, OpenAI, Fireworks and OpenRouter.

Pick one in `.env` (copy `.env.example` to `.env`; `.env` is gitignored, never commit a key):

    HEIST_LLM_PROVIDER=anthropic     # anthropic | openai | fireworks | openrouter
    HEIST_LLM_MODEL=                 # optional for anthropic, required for the others
    ANTHROPIC_API_KEY=...            # the key of the provider you picked

Then:

    from heist.llm import get_llm
    llm = get_llm()
    llm.text("Summarize this statement: ...")            # -> str
    llm.json("Extract the claims: ...", schema={...})    # -> dict matching the JSON schema

Claude goes through the official `anthropic` SDK. OpenAI, Fireworks and OpenRouter go through
the `openai` SDK, pointed at each provider's OpenAI-compatible endpoint. `uv run heist llm`
checks your setup with two tiny calls.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from .case import ROOT


class LLMError(RuntimeError):
    """Anything that stops a call: setup, credentials, the provider, or an answer that isn't usable."""


@dataclass(frozen=True)
class Provider:
    name: str
    key_env: str
    base_url: str | None
    default_model: str | None
    keys_at: str


PROVIDERS = {
    p.name: p
    for p in [
        Provider("anthropic", "ANTHROPIC_API_KEY", None, "claude-opus-5-5", "https://platform.claude.com"),
        Provider("openai", "OPENAI_API_KEY", None, None, "https://platform.openai.com"),
        Provider(
            "fireworks", "FIREWORKS_API_KEY", "https://api.fireworks.ai/inference/v1", None, "https://fireworks.ai"
        ),
        Provider("openrouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", None, "https://openrouter.ai"),
    ]
}

# Claude models that take a server-side fallback when a safety classifier declines a request.
CLAUDE_FALLBACKS = {"claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
MAX_TOKENS = 16000


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover
        return
    load_dotenv(ROOT / ".env")
    load_dotenv()  # and a .env in the current folder, if you run from elsewhere
    # An empty KEY= line from the template must not count as a key: it would shadow other credentials.
    for p in PROVIDERS.values():
        if os.environ.get(p.key_env) == "":
            del os.environ[p.key_env]


@dataclass
class Usage:
    calls: int = 0
    cached: int = 0  # answers read from .heist-cache instead of calling the provider
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class LLM:
    provider: Provider
    model: str
    effort: str | None = None  # Claude only: low | medium | high | xhigh | max
    usage: Usage = field(default_factory=Usage)
    _client: Any = None

    def __repr__(self) -> str:
        return f"<LLM {self.provider.name}:{self.model}>"

    # ── Public calls ─────────────────────────────────────────────────────────

    def text(self, prompt: str, system: str | None = None) -> str:
        """One answer as plain text."""
        return self._call(prompt, system, None)

    def json(self, prompt: str, schema: dict, system: str | None = None) -> dict:
        """One answer as JSON that follows `schema` (a JSON Schema object).

        Use `"additionalProperties": false` and list every property in `required`: OpenAI's strict
        mode needs both, and every provider here accepts them.
        """
        raw = self._call(prompt, system, schema)
        try:
            value = json.loads(_strip_fences(raw))
        except json.JSONDecodeError as e:
            raise LLMError(f"{self}: the answer isn't valid JSON ({e.msg}): {raw[:200]!r}") from e
        if not isinstance(value, dict):
            raise LLMError(f"{self}: expected a JSON object, got {type(value).__name__}")
        return value

    # ── Providers ────────────────────────────────────────────────────────────

    def _call(self, prompt: str, system: str | None, schema: dict | None) -> str:
        """Answers are cached on disk (.heist-cache/llm), so rerunning the checks costs nothing.

        Set HEIST_LLM_CACHE=0 to always call the provider.
        """
        use_cache = os.environ.get("HEIST_LLM_CACHE", "1") != "0"
        key = hashlib.sha256(
            json.dumps([self.provider.name, self.model, self.effort, system, prompt, schema], sort_keys=True).encode()
        ).hexdigest()
        path = ROOT / ".heist-cache" / "llm" / f"{key}.json"
        if use_cache and path.exists():
            self.usage.cached += 1
            return json.loads(path.read_text(encoding="utf-8"))["answer"]
        if self.provider.name == "anthropic":
            answer = self._claude(prompt, system, schema)
        else:
            answer = self._openai_compatible(prompt, system, schema)
        if use_cache:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"model": self.model, "answer": answer}), encoding="utf-8")
        return answer

    def _claude(self, prompt: str, system: str | None, schema: dict | None) -> str:
        import anthropic

        if self._client is None:
            key = os.environ.get(self.provider.key_env)
            # Without a key, the SDK still finds an `ant auth login` profile if there is one.
            self._client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            request["system"] = system
            request["cache_control"] = {"type": "ephemeral"}  # repeated system prompts are read from cache
        output_config: dict[str, Any] = {}
        if self.effort:
            output_config["effort"] = self.effort
        if schema:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        if output_config:
            request["output_config"] = output_config
        try:
            if self.model in CLAUDE_FALLBACKS:
                # If a safety classifier declines, the API retries on a fallback model in the same call.
                response = self._client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default", **request
                )
            else:
                response = self._client.messages.create(**request)
        except anthropic.AuthenticationError as e:
            raise LLMError(f"{self}: the key in {self.provider.key_env} was rejected") from e
        except anthropic.NotFoundError as e:
            raise LLMError(f"{self}: no model {self.model!r} (check HEIST_LLM_MODEL)") from e
        except anthropic.RateLimitError as e:
            raise LLMError(f"{self}: rate limited, try again in a minute") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"{self}: the API answered {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError(f"{self}: can't reach the API ({e})") from e
        self._count(response.usage.input_tokens, response.usage.output_tokens)
        if response.stop_reason == "refusal":
            raise LLMError(f"{self}: the model declined this request")
        if response.stop_reason == "max_tokens":
            raise LLMError(f"{self}: the answer hit the {MAX_TOKENS}-token limit before it finished")
        return "".join(block.text for block in response.content if block.type == "text")

    def _openai_compatible(self, prompt: str, system: str | None, schema: dict | None) -> str:
        import openai

        if self._client is None:
            key = os.environ.get(self.provider.key_env)
            if not key:
                raise LLMError(
                    f"Set {self.provider.key_env} in .env for provider {self.provider.name!r} "
                    f"(get a key at {self.provider.keys_at})"
                )
            self._client = openai.OpenAI(api_key=key, base_url=self.provider.base_url)
        messages = [{"role": "system", "content": system}] if system else []
        messages.append({"role": "user", "content": prompt})
        request: dict[str, Any] = {"model": self.model, "messages": messages}
        if schema:
            request["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "answer", "schema": schema, "strict": True},
            }
        try:
            try:
                response = self._client.chat.completions.create(**request)
            except openai.BadRequestError:
                if not schema:
                    raise
                # Some models behind Fireworks or OpenRouter don't take a JSON schema: ask in words instead.
                request["response_format"] = {"type": "json_object"}
                request["messages"] = [
                    *messages[:-1],
                    {"role": "user", "content": f"{prompt}\n\nAnswer with JSON only, following this JSON Schema:\n"
                     f"{json.dumps(schema)}"},
                ]  # fmt: skip
                response = self._client.chat.completions.create(**request)
        except openai.AuthenticationError as e:
            raise LLMError(f"{self}: the key in {self.provider.key_env} was rejected") from e
        except openai.NotFoundError as e:
            raise LLMError(f"{self}: no model {self.model!r} at {self.provider.name} (check HEIST_LLM_MODEL)") from e
        except openai.RateLimitError as e:
            raise LLMError(f"{self}: rate limited, try again in a minute") from e
        except openai.APIStatusError as e:
            raise LLMError(f"{self}: the API answered {e.status_code}: {e.message}") from e
        except openai.APIConnectionError as e:
            raise LLMError(f"{self}: can't reach {self.provider.base_url or 'the API'} ({e})") from e
        if response.usage:
            self._count(response.usage.prompt_tokens, response.usage.completion_tokens)
        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise LLMError(f"{self}: the answer was cut off at the model's length limit")
        if getattr(choice.message, "refusal", None):
            raise LLMError(f"{self}: the model declined this request")
        return choice.message.content or ""

    def _count(self, input_tokens: int | None, output_tokens: int | None) -> None:
        self.usage.calls += 1
        self.usage.input_tokens += input_tokens or 0
        self.usage.output_tokens += output_tokens or 0


def _strip_fences(text: str) -> str:
    """Some models wrap JSON in ```json fences even when asked not to."""
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return match.group(1) if match else text.strip()


def get_llm(provider: str | None = None, model: str | None = None) -> LLM:
    """The LLM configured in .env (or the provider and model you pass)."""
    _load_env()
    name = (provider or os.environ.get("HEIST_LLM_PROVIDER") or "").strip().lower()
    if not name:
        raise LLMError("Set HEIST_LLM_PROVIDER in .env: copy .env.example to .env and pick a provider")
    if name not in PROVIDERS:
        raise LLMError(f"Unknown HEIST_LLM_PROVIDER {name!r}: use one of {', '.join(PROVIDERS)}")
    p = PROVIDERS[name]
    chosen = (model or os.environ.get("HEIST_LLM_MODEL") or p.default_model or "").strip()
    if not chosen:
        raise LLMError(f"Set HEIST_LLM_MODEL in .env: {name} has no default model (use an id from its model list)")
    effort = (os.environ.get("HEIST_LLM_EFFORT") or "").strip() or None
    if effort and name != "anthropic":
        effort = None  # an effort setting only applies to Claude
    return LLM(p, chosen, effort)
