from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Protocol, Sequence

import httpx


TaskName = Literal["tutor", "quiz", "concept", "vision", "embedding", "verification"]
ProviderName = Literal[
    "disabled",
    "groq",
    "openrouter",
    "gemini",
    "openai_compatible",
    "ollama",
]
Capability = Literal["chat", "vision", "embeddings", "json"]

TASK_NAMES: tuple[TaskName, ...] = (
    "tutor",
    "quiz",
    "concept",
    "vision",
    "embedding",
    "verification",
)
_PROVIDER_DEFAULT_URLS: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "ollama": "http://127.0.0.1:11434",
}
_PROVIDER_KEY_ENV: dict[str, str] = {
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


class ModelRoutingError(RuntimeError):
    """Base error with safe, non-secret diagnostics."""


class ModelDisabledError(ModelRoutingError):
    pass


class ModelCredentialsError(ModelRoutingError):
    pass


class ModelAuthenticationError(ModelRoutingError):
    pass


class ModelCapabilityError(ModelRoutingError):
    pass


class ModelUnavailableError(ModelRoutingError):
    pass


class ModelRateLimitError(ModelRoutingError):
    pass


class ModelTimeoutError(ModelRoutingError):
    pass


class ModelNetworkError(ModelRoutingError):
    pass


class ModelOutputError(ModelRoutingError):
    pass


@dataclass(frozen=True, slots=True)
class ModelMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class TaskModelConfig:
    task: TaskName
    enabled: bool = False
    provider: ProviderName = "disabled"
    model: str = ""
    max_tokens: int | None = None
    base_url: str | None = None
    capabilities: frozenset[Capability] = frozenset({"chat"})
    fallback_provider: ProviderName = "disabled"
    fallback_model: str = ""
    fallback_base_url: str | None = None
    fallback_capabilities: frozenset[Capability] = frozenset({"chat"})
    api_key: str | None = field(default=None, repr=False, compare=False)

    @property
    def effective_base_url(self) -> str | None:
        return self.base_url or _PROVIDER_DEFAULT_URLS.get(self.provider)

    @property
    def fallback_configured(self) -> bool:
        return self.fallback_provider != "disabled" and bool(self.fallback_model)


@dataclass(frozen=True, slots=True)
class ModelResult:
    task: TaskName
    provider: ProviderName
    model: str
    text: str
    used_fallback: bool = False


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    task: TaskName
    provider: ProviderName
    model: str
    vectors: tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class ModelStatus:
    task: TaskName
    enabled: bool
    provider: ProviderName
    model: str | None
    capabilities: tuple[str, ...]
    fallback_provider: ProviderName | None
    fallback_model: str | None


class ProviderAdapter(Protocol):
    def complete(
        self,
        config: TaskModelConfig,
        messages: Sequence[ModelMessage],
        *,
        timeout_seconds: float,
        max_tokens: int | None,
        transport: httpx.BaseTransport | None = None,
    ) -> str: ...


class VisionAdapter(Protocol):
    def describe_image(
        self,
        config: TaskModelConfig,
        prompt: str,
        image_data: bytes,
        mime_type: str,
        *,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> str: ...


class EmbeddingAdapter(Protocol):
    def embed(
        self,
        config: TaskModelConfig,
        texts: Sequence[str],
        *,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> tuple[tuple[float, ...], ...]: ...


class HttpProviderAdapter:
    def complete(
        self,
        config: TaskModelConfig,
        messages: Sequence[ModelMessage],
        *,
        timeout_seconds: float,
        max_tokens: int | None,
        transport: httpx.BaseTransport | None = None,
    ) -> str:
        raise NotImplementedError

    @staticmethod
    def _post_json(
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout_seconds: float,
        transport: httpx.BaseTransport | None,
    ) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=timeout_seconds, transport=transport) as client:
                response = client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError("Configured model request timed out.") from exc
        except httpx.HTTPError as exc:
            raise ModelNetworkError("Network connection to configured provider failed.") from exc

        if response.status_code in (401, 403):
            raise ModelAuthenticationError("Configured provider rejected authentication.")
        if response.status_code == 429:
            raise ModelRateLimitError("Configured model provider rate-limited the request.")
        if response.status_code >= 500:
            raise ModelUnavailableError("Configured model provider is unavailable.")
        if response.is_error:
            raise ModelUnavailableError(
                f"Configured model provider rejected the request (HTTP {response.status_code})."
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise ModelOutputError("Configured model provider returned malformed JSON.") from exc
        if not isinstance(body, dict):
            raise ModelOutputError("Configured model provider returned an unexpected response.")
        return body


class OpenAICompatibleAdapter(HttpProviderAdapter):
    def complete(
        self,
        config: TaskModelConfig,
        messages: Sequence[ModelMessage],
        *,
        timeout_seconds: float,
        max_tokens: int | None,
        transport: httpx.BaseTransport | None = None,
    ) -> str:
        base_url = config.effective_base_url
        if not base_url:
            raise ModelUnavailableError("No base URL is configured for this provider.")
        headers = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        payload: dict[str, Any] = {
            "model": config.model,
            "messages": [{"role": item.role, "content": item.content} for item in messages],
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        body = self._post_json(
            f"{base_url.rstrip('/')}/chat/completions",
            payload,
            headers,
            timeout_seconds,
            transport,
        )
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelOutputError("Configured model provider returned malformed chat output.") from exc
        if not isinstance(content, str) or not content.strip():
            raise ModelOutputError("Configured model provider returned empty chat output.")
        return content

    def describe_image(
        self,
        config: TaskModelConfig,
        prompt: str,
        image_data: bytes,
        mime_type: str,
        *,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> str:
        base_url = config.effective_base_url
        if not base_url:
            raise ModelUnavailableError("No base URL is configured for this provider.")
        headers = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        payload: dict[str, Any] = {
            "model": config.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64.b64encode(image_data).decode('ascii')}"
                        },
                    },
                ],
            }],
        }
        if config.max_tokens is not None:
            payload["max_tokens"] = config.max_tokens
        body = self._post_json(
            f"{base_url.rstrip('/')}/chat/completions",
            payload,
            headers,
            timeout_seconds,
            transport,
        )
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelOutputError("Configured vision provider returned malformed output.") from exc
        if not isinstance(text, str) or not text.strip():
            raise ModelOutputError("Configured vision provider returned empty output.")
        return text

    def embed(
        self,
        config: TaskModelConfig,
        texts: Sequence[str],
        *,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> tuple[tuple[float, ...], ...]:
        base_url = config.effective_base_url
        if not base_url:
            raise ModelUnavailableError("No base URL is configured for this provider.")
        headers = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        body = self._post_json(
            f"{base_url.rstrip('/')}/embeddings",
            {"model": config.model, "input": list(texts)},
            headers,
            timeout_seconds,
            transport,
        )
        try:
            data = body["data"]
            indexed_vectors = sorted(data, key=lambda row: row["index"])
            vectors = tuple(tuple(float(value) for value in row["embedding"]) for row in indexed_vectors)
        except (KeyError, TypeError, ValueError) as exc:
            raise ModelOutputError("Configured embedding provider returned malformed vectors.") from exc
        if len(vectors) != len(texts) or not vectors or any(not vector for vector in vectors):
            raise ModelOutputError("Configured embedding provider returned the wrong vector count.")
        return vectors


class GeminiAdapter(HttpProviderAdapter):
    def complete(
        self,
        config: TaskModelConfig,
        messages: Sequence[ModelMessage],
        *,
        timeout_seconds: float,
        max_tokens: int | None,
        transport: httpx.BaseTransport | None = None,
    ) -> str:
        base_url = config.effective_base_url
        if not base_url:
            raise ModelUnavailableError("No base URL is configured for Gemini.")
        if not config.api_key:
            raise ModelCredentialsError("Gemini credentials are not configured.")
        system_messages = [message.content for message in messages if message.role == "system"]
        contents = [
            {
                "role": "model" if message.role == "assistant" else "user",
                "parts": [{"text": message.content}],
            }
            for message in messages
            if message.role != "system"
        ]
        payload: dict[str, Any] = {"contents": contents}
        if system_messages:
            payload["systemInstruction"] = {"parts": [{"text": "\n".join(system_messages)}]}
        if max_tokens is not None:
            payload["generationConfig"] = {"maxOutputTokens": max_tokens}
        body = self._post_json(
            f"{base_url.rstrip('/')}/models/{config.model}:generateContent",
            payload,
            {"Content-Type": "application/json", "x-goog-api-key": config.api_key},
            timeout_seconds,
            transport,
        )
        try:
            parts = body["candidates"][0]["content"]["parts"]
            text = "".join(part["text"] for part in parts if isinstance(part, dict) and "text" in part)
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelOutputError("Gemini returned malformed chat output.") from exc
        if not text.strip():
            raise ModelOutputError("Gemini returned empty chat output.")
        return text

    def describe_image(
        self,
        config: TaskModelConfig,
        prompt: str,
        image_data: bytes,
        mime_type: str,
        *,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> str:
        base_url = config.effective_base_url
        if not base_url:
            raise ModelUnavailableError("No base URL is configured for Gemini.")
        if not config.api_key:
            raise ModelCredentialsError("Gemini credentials are not configured.")
        payload: dict[str, Any] = {
            "contents": [{
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": base64.b64encode(image_data).decode("ascii"),
                        }
                    },
                ],
            }]
        }
        if config.max_tokens is not None:
            payload["generationConfig"] = {"maxOutputTokens": config.max_tokens}
        body = self._post_json(
            f"{base_url.rstrip('/')}/models/{config.model}:generateContent",
            payload,
            {"Content-Type": "application/json", "x-goog-api-key": config.api_key},
            timeout_seconds,
            transport,
        )
        try:
            parts = body["candidates"][0]["content"]["parts"]
            text = "".join(part["text"] for part in parts if isinstance(part, dict) and "text" in part)
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelOutputError("Gemini returned malformed vision output.") from exc
        if not text.strip():
            raise ModelOutputError("Gemini returned empty vision output.")
        return text

    def embed(
        self,
        config: TaskModelConfig,
        texts: Sequence[str],
        *,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> tuple[tuple[float, ...], ...]:
        base_url = config.effective_base_url
        if not base_url:
            raise ModelUnavailableError("No base URL is configured for Gemini.")
        if not config.api_key:
            raise ModelCredentialsError("Gemini credentials are not configured.")
        vectors = []
        for text in texts:
            body = self._post_json(
                f"{base_url.rstrip('/')}/models/{config.model}:embedContent",
                {"content": {"parts": [{"text": text}]}},
                {"Content-Type": "application/json", "x-goog-api-key": config.api_key},
                timeout_seconds,
                transport,
            )
            try:
                vector = tuple(float(value) for value in body["embedding"]["values"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ModelOutputError("Gemini returned malformed embedding output.") from exc
            if not vector:
                raise ModelOutputError("Gemini returned an empty embedding.")
            vectors.append(vector)
        return tuple(vectors)


_ADAPTERS: dict[str, ProviderAdapter] = {
    "groq": OpenAICompatibleAdapter(),
    "openrouter": OpenAICompatibleAdapter(),
    "openai_compatible": OpenAICompatibleAdapter(),
    "ollama": OpenAICompatibleAdapter(),
    "gemini": GeminiAdapter(),
}
_RETRYABLE_ERRORS = (
    ModelUnavailableError,
    ModelRateLimitError,
    ModelTimeoutError,
    ModelNetworkError,
)


def _env_bool(
    name: str,
    default: bool = False,
    environ: Mapping[str, str] | None = None,
) -> bool:
    env = os.environ if environ is None else environ
    value = env.get(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _task_env_name(task: str, suffix: str) -> str:
    return f"NEXUS_{task.upper()}_{suffix}"


def load_task_config(task: TaskName, environ: Mapping[str, str] | None = None) -> TaskModelConfig:
    env = os.environ if environ is None else environ
    prefix = f"NEXUS_{task.upper()}_"
    provider = env.get(prefix + "PROVIDER", "disabled").strip().casefold()
    if provider not in _ADAPTERS and provider != "disabled":
        provider = "disabled"
    try:
        max_tokens = int(env[prefix + "MAX_TOKENS"]) if env.get(prefix + "MAX_TOKENS") else None
    except ValueError:
        max_tokens = None
    if max_tokens is not None and max_tokens < 1:
        max_tokens = None
    capability_values = {item.strip().casefold() for item in env.get(prefix + "CAPABILITIES", "chat").split(",") if item.strip()}
    capabilities = frozenset(
        item for item in capability_values if item in {"chat", "vision", "embeddings", "json"}
    )
    key_name = _PROVIDER_KEY_ENV.get(provider)
    enabled = (
        _env_bool(prefix + "ENABLED", False, env)
        and provider != "disabled"
        and bool(env.get(prefix + "MODEL", "").strip())
    )
    fallback_provider = env.get(prefix + "FALLBACK_PROVIDER", "disabled").strip().casefold()
    if fallback_provider not in _ADAPTERS and fallback_provider != "disabled":
        fallback_provider = "disabled"
    fallback_key_name = _PROVIDER_KEY_ENV.get(fallback_provider)
    fallback_capability_values = {
        item.strip().casefold()
        for item in env.get(prefix + "FALLBACK_CAPABILITIES", "chat").split(",")
        if item.strip()
    }
    fallback_capabilities = frozenset(
        item
        for item in fallback_capability_values
        if item in {"chat", "vision", "embeddings", "json"}
    )
    return TaskModelConfig(
        task=task,
        enabled=enabled,
        provider=provider,  # type: ignore[arg-type]
        model=env.get(prefix + "MODEL", "").strip(),
        max_tokens=max_tokens,
        base_url=env.get(prefix + "BASE_URL") or None,
        capabilities=capabilities,  # type: ignore[arg-type]
        fallback_provider=fallback_provider,  # type: ignore[arg-type]
        fallback_model=env.get(prefix + "FALLBACK_MODEL", "").strip(),
        fallback_base_url=env.get(prefix + "FALLBACK_BASE_URL") or None,
        api_key=env.get(prefix + "API_KEY") or (env.get(key_name, "") if key_name else "") or None,
        fallback_capabilities=fallback_capabilities,  # type: ignore[arg-type]
    )


class ModelRouter:
    def __init__(
        self,
        configs: Mapping[TaskName, TaskModelConfig] | None = None,
        *,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.configs = dict(configs or {task: load_task_config(task) for task in TASK_NAMES})
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else self._read_timeout()
        self.max_retries = max_retries if max_retries is not None else self._read_retries()
        self.transport = transport

    @staticmethod
    def _read_timeout() -> float:
        try:
            return min(max(float(os.environ.get("NEXUS_MODEL_TIMEOUT_SECONDS", "20")), 0.1), 300.0)
        except ValueError:
            return 20.0

    @staticmethod
    def _read_retries() -> int:
        try:
            return min(max(int(os.environ.get("NEXUS_MODEL_MAX_RETRIES", "0")), 0), 5)
        except ValueError:
            return 0

    def status(self) -> list[ModelStatus]:
        statuses = []
        for task in TASK_NAMES:
            config = self.configs.get(task, TaskModelConfig(task=task))
            statuses.append(
                ModelStatus(
                    task=task,
                    enabled=config.enabled,
                    provider=config.provider if config.enabled else "disabled",
                    model=config.model if config.enabled else None,
                    capabilities=tuple(sorted(config.capabilities)) if config.enabled else (),
                    fallback_provider=config.fallback_provider if config.fallback_configured else None,
                    fallback_model=config.fallback_model if config.fallback_configured else None,
                )
            )
        return statuses

    def complete(
        self,
        task: TaskName,
        messages: Sequence[ModelMessage],
        *,
        required_capabilities: frozenset[Capability] = frozenset({"chat"}),
    ) -> ModelResult:
        config = self.configs.get(task, TaskModelConfig(task=task))
        if not config.enabled:
            raise ModelDisabledError(f"Model task '{task}' is disabled.")
        missing = required_capabilities - config.capabilities
        if missing:
            raise ModelCapabilityError(
                f"Configured model for task '{task}' lacks required capabilities: {', '.join(sorted(missing))}."
            )
        try:
            text = self._complete_with_retries(config, messages)
            return ModelResult(task, config.provider, config.model, text)
        except (*_RETRYABLE_ERRORS, ModelCredentialsError):
            if not config.fallback_configured:
                raise
            fallback = TaskModelConfig(
                task=task,
                enabled=True,
                provider=config.fallback_provider,
                model=config.fallback_model,
                max_tokens=config.max_tokens,
                base_url=config.fallback_base_url,
                capabilities=config.fallback_capabilities,
                api_key=self._key_for_provider(config.fallback_provider),
            )
            if required_capabilities - fallback.capabilities:
                raise ModelCapabilityError(
                    f"Configured fallback for task '{task}' lacks the required capabilities."
                )
            text = self._complete_with_retries(fallback, messages)
            return ModelResult(task, fallback.provider, fallback.model, text, used_fallback=True)

    def describe_image(self, task: TaskName, prompt: str, image_data: bytes, mime_type: str) -> ModelResult:
        config = self.configs.get(task, TaskModelConfig(task=task))
        self._require_task_capability(config, "vision")
        if not image_data or len(image_data) > 10 * 1024 * 1024:
            raise ModelOutputError("Image input is empty or exceeds the 10 MiB request limit.")
        if mime_type not in {"image/png", "image/jpeg", "image/gif", "image/webp"}:
            raise ModelCapabilityError("Configured vision task does not accept this image format.")
        adapter = _ADAPTERS.get(config.provider)
        if adapter is None or not hasattr(adapter, "describe_image"):
            raise ModelCapabilityError("Configured provider has no implemented vision adapter.")
        key_name = _PROVIDER_KEY_ENV.get(config.provider)
        if key_name and not config.api_key:
            raise ModelCredentialsError(f"Credentials for configured provider '{config.provider}' are missing.")
        if not config.model:
            raise ModelDisabledError(f"No model is configured for task '{task}'.")
        text = adapter.describe_image(  # type: ignore[attr-defined]
            config,
            prompt,
            image_data,
            mime_type,
            timeout_seconds=self.timeout_seconds,
            transport=self.transport,
        )
        return ModelResult(task, config.provider, config.model, text)

    def embed(self, task: TaskName, texts: Sequence[str]) -> EmbeddingResult:
        config = self.configs.get(task, TaskModelConfig(task=task))
        self._require_task_capability(config, "embeddings")
        if not texts or any(not text.strip() for text in texts):
            raise ModelOutputError("Embedding input must contain non-empty text values.")
        adapter = _ADAPTERS.get(config.provider)
        if adapter is None or not hasattr(adapter, "embed"):
            raise ModelCapabilityError("Configured provider has no implemented embedding adapter.")
        key_name = _PROVIDER_KEY_ENV.get(config.provider)
        if key_name and not config.api_key:
            raise ModelCredentialsError(f"Credentials for configured provider '{config.provider}' are missing.")
        if not config.model:
            raise ModelDisabledError(f"No model is configured for task '{task}'.")
        vectors = adapter.embed(  # type: ignore[attr-defined]
            config,
            texts,
            timeout_seconds=self.timeout_seconds,
            transport=self.transport,
        )
        return EmbeddingResult(task, config.provider, config.model, vectors)

    @staticmethod
    def _require_task_capability(config: TaskModelConfig, capability: Capability) -> None:
        if not config.enabled:
            raise ModelDisabledError(f"Model task '{config.task}' is disabled.")
        if capability not in config.capabilities:
            raise ModelCapabilityError(
                f"Configured model for task '{config.task}' lacks required capability '{capability}'."
            )

    def _key_for_provider(self, provider: ProviderName) -> str | None:
        name = _PROVIDER_KEY_ENV.get(provider)
        return os.environ.get(name) if name else None

    def _complete_with_retries(
        self,
        config: TaskModelConfig,
        messages: Sequence[ModelMessage],
    ) -> str:
        key_name = _PROVIDER_KEY_ENV.get(config.provider)
        if key_name and not config.api_key:
            raise ModelCredentialsError(f"Credentials for configured provider '{config.provider}' are missing.")
        adapter = _ADAPTERS.get(config.provider)
        if adapter is None:
            raise ModelDisabledError(f"Provider '{config.provider}' is not enabled.")
        if not config.model:
            raise ModelDisabledError(f"No model is configured for task '{config.task}'.")

        for attempt in range(self.max_retries + 1):
            try:
                return adapter.complete(
                    config,
                    messages,
                    timeout_seconds=self.timeout_seconds,
                    max_tokens=config.max_tokens,
                    transport=self.transport,
                )
            except _RETRYABLE_ERRORS:
                if attempt >= self.max_retries:
                    raise
        raise ModelUnavailableError("Configured model provider is unavailable.")


def safe_diagnostic_text(error: Exception) -> str:
    """Return a static safe message; never stringify provider exceptions or response bodies."""
    if isinstance(error, ModelCredentialsError):
        return "Configured provider credentials are missing."
    if isinstance(error, ModelAuthenticationError):
        return "Configured provider rejected authentication; verify the key and account access."
    if isinstance(error, ModelRateLimitError):
        return "Configured provider rate-limited the request."
    if isinstance(error, ModelTimeoutError):
        return "Configured provider request timed out."
    if isinstance(error, ModelNetworkError):
        return "Network connection to configured provider failed."
    if isinstance(error, ModelCapabilityError):
        return "Configured model lacks the capability required for this task."
    if isinstance(error, ModelOutputError):
        return "Configured provider returned unusable output."
    if isinstance(error, ModelDisabledError):
        return "Model task is disabled."
    return "Configured provider is unavailable."
