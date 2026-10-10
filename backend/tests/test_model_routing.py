import json
import sqlite3
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app import documents
from app.answering import RoutedEvidenceAnswerer
from app.ingestion import ExtractedRecord
from app.main import app
from app.model_smoke import run_smoke
from app.model_routing import (
    ModelAuthenticationError,
    ModelCapabilityError,
    ModelCredentialsError,
    ModelDisabledError,
    ModelMessage,
    ModelOutputError,
    ModelRateLimitError,
    ModelRouter,
    ModelTimeoutError,
    ModelUnavailableError,
    TaskModelConfig,
    load_task_config,
    safe_diagnostic_text,
)


def test_all_task_configs_default_disabled_without_provider_calls() -> None:
    router = ModelRouter()

    statuses = router.status()

    assert len(statuses) == 6
    assert all(not status.enabled and status.provider == "disabled" for status in statuses)
    with pytest.raises(ModelDisabledError):
        router.complete("tutor", [ModelMessage("user", "hello")])


def test_routing_configuration_is_independent_per_task() -> None:
    env = {
        "NEXUS_TUTOR_ENABLED": "true",
        "NEXUS_TUTOR_PROVIDER": "groq",
        "NEXUS_TUTOR_MODEL": "tutor-configurable-id",
        "NEXUS_QUIZ_ENABLED": "true",
        "NEXUS_QUIZ_PROVIDER": "openrouter",
        "NEXUS_QUIZ_MODEL": "quiz-configurable-id",
        "GROQ_API_KEY": "tutor-test-key",
        "OPENROUTER_API_KEY": "quiz-test-key",
    }

    tutor = load_task_config("tutor", env)
    quiz = load_task_config("quiz", env)

    assert (tutor.provider, tutor.model, tutor.enabled) == (
        "groq", "tutor-configurable-id", True
    )
    assert (quiz.provider, quiz.model, quiz.enabled) == (
        "openrouter", "quiz-configurable-id", True
    )
    assert tutor.api_key != quiz.api_key
    assert "tutor-test-key" not in repr(tutor)
    assert "quiz-test-key" not in repr(quiz)


def _router(
    provider: str,
    model: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    capabilities: frozenset[str] = frozenset({"chat"}),
    transport: httpx.BaseTransport | None = None,
    max_retries: int = 0,
) -> ModelRouter:
    config = TaskModelConfig(
        task="tutor",
        enabled=True,
        provider=provider,  # type: ignore[arg-type]
        model=model,
        base_url=base_url,
        api_key=api_key,
        capabilities=capabilities,  # type: ignore[arg-type]
    )
    return ModelRouter({"tutor": config}, transport=transport, max_retries=max_retries)


def test_openai_compatible_adapter_posts_configured_model_and_parses_text() -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["headers"] = dict(request.headers)
        observed["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "grounded"}}]})

    router = _router(
        "openai_compatible",
        "local-test-model",
        base_url="http://mock/v1",
        api_key="never-log-this",
        transport=httpx.MockTransport(handler),
    )
    result = router.complete("tutor", [ModelMessage("user", "question")])

    assert result.text == "grounded"
    assert result.provider == "openai_compatible"
    assert observed["url"] == "http://mock/v1/chat/completions"
    assert observed["payload"]["model"] == "local-test-model"
    assert observed["headers"]["authorization"] == "Bearer never-log-this"
    assert "never-log-this" not in repr(router.status())


def test_groq_and_openrouter_use_openai_compatible_adapters() -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    for provider, base_url, api_key in (
        ("groq", "https://api.groq.test/openai/v1", "groq-key"),
        ("openrouter", "https://openrouter.test/api/v1", "router-key"),
    ):
        router = _router(
            provider,
            f"{provider}-model",
            base_url=base_url,
            api_key=api_key,
            transport=httpx.MockTransport(handler),
        )
        assert router.complete("tutor", [ModelMessage("user", "test")]).text == "ok"

    assert seen_urls == [
        "https://api.groq.test/openai/v1/chat/completions",
        "https://openrouter.test/api/v1/chat/completions",
    ]


def test_ollama_uses_only_the_configured_local_openai_compatible_url() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, json={"choices": [{"message": {"content": "local response"}}]})

    router = _router(
        "ollama",
        "operator-selected-local-id",
        base_url="http://127.0.0.1:11434/v1",
        transport=httpx.MockTransport(handler),
    )
    result = router.complete("tutor", [ModelMessage("user", "local test")])

    assert result.text == "local response"
    assert requested_urls == ["http://127.0.0.1:11434/v1/chat/completions"]


def test_gemini_adapter_uses_header_credentials_and_native_payload() -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["key"] = request.headers.get("x-goog-api-key")
        observed["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "Gemini result"}]}}]},
        )

    router = _router(
        "gemini",
        "configured-gemini-id",
        base_url="https://gemini.test/v1beta",
        api_key="gemini-secret",
        transport=httpx.MockTransport(handler),
    )
    result = router.complete(
        "tutor",
        [ModelMessage("system", "system"), ModelMessage("user", "question")],
    )

    assert result.text == "Gemini result"
    assert observed["url"] == "https://gemini.test/v1beta/models/configured-gemini-id:generateContent"
    assert observed["key"] == "gemini-secret"
    assert observed["body"]["systemInstruction"]["parts"][0]["text"] == "system"
    assert "gemini-secret" not in observed["url"]


def test_gemini_vision_and_embedding_payloads_are_capability_routed() -> None:
    observed: list[tuple[str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        observed.append((str(request.url), payload))
        if request.url.path.endswith(":embedContent"):
            return httpx.Response(200, json={"embedding": {"values": [0.5, 0.25]}})
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "visible geometry"}]}}]},
        )

    config = TaskModelConfig(
        task="vision",
        enabled=True,
        provider="gemini",
        model="configured-multimodal-model",
        base_url="https://gemini.test/v1beta",
        api_key="gemini-test-key",
        capabilities=frozenset({"chat", "vision", "embeddings"}),
    )
    router = ModelRouter({"vision": config}, transport=httpx.MockTransport(handler))

    vision_result = router.describe_image("vision", "Describe only visible geometry.", b"image", "image/png")
    embedding_result = router.embed("vision", ["synthetic text"])

    assert vision_result.text == "visible geometry"
    assert embedding_result.vectors == ((0.5, 0.25),)
    assert observed[0][1]["contents"][0]["parts"][1]["inlineData"]["mimeType"] == "image/png"
    assert observed[1][1]["content"]["parts"][0]["text"] == "synthetic text"


def test_openai_compatible_vision_and_embeddings_require_declared_capabilities() -> None:
    observed: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        observed.append(body)
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(
                200,
                json={"data": [
                    {"index": 0, "embedding": [0.1, 0.2]},
                    {"index": 1, "embedding": [0.3, 0.4]},
                ]},
            )
        return httpx.Response(200, json={"choices": [{"message": {"content": "diagram description"}}]})

    config = TaskModelConfig(
        task="vision",
        enabled=True,
        provider="openai_compatible",
        model="multimodal-model",
        base_url="http://mock/v1",
        capabilities=frozenset({"chat", "vision", "embeddings"}),
    )
    router = ModelRouter(
        {"vision": config, "embedding": TaskModelConfig(
            task="embedding",
            enabled=True,
            provider="openai_compatible",
            model="embedding-model",
            base_url="http://mock/v1",
            capabilities=frozenset({"chat", "embeddings"}),
        )},
        transport=httpx.MockTransport(handler),
    )
    image_result = router.describe_image("vision", "Describe visible objects only.", b"png-bytes", "image/png")
    embedding_result = router.embed("embedding", ["first", "second"])

    assert image_result.text == "diagram description"
    assert "data:image/png;base64," in observed[0]["messages"][0]["content"][1]["image_url"]["url"]
    assert embedding_result.vectors == ((0.1, 0.2), (0.3, 0.4))


def test_explicit_fallback_is_used_for_missing_credentials_only_when_configured() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith("http://local.test/")
        return httpx.Response(200, json={"choices": [{"message": {"content": "local fallback"}}]})

    config = TaskModelConfig(
        task="tutor",
        enabled=True,
        provider="groq",
        model="cloud-model-id",
        fallback_provider="openai_compatible",
        fallback_model="local-ollama-model-id",
        fallback_base_url="http://local.test/v1",
        fallback_capabilities=frozenset({"chat"}),
    )
    router = ModelRouter({"tutor": config}, transport=httpx.MockTransport(handler))
    result = router.complete("tutor", [ModelMessage("user", "question")])

    assert result.text == "local fallback"
    assert result.used_fallback is True
    assert result.provider == "openai_compatible"
    assert result.model == "local-ollama-model-id"


def test_explicit_fallback_is_used_after_rate_limit() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.host == "cloud.test":
            return httpx.Response(429, text="provider-secret-details")
        return httpx.Response(200, json={"choices": [{"message": {"content": "fallback output"}}]})

    config = TaskModelConfig(
        task="tutor",
        enabled=True,
        provider="groq",
        model="cloud-id",
        base_url="https://cloud.test/v1",
        api_key="cloud-test-key",
        fallback_provider="openai_compatible",
        fallback_model="local-id",
        fallback_base_url="http://local.test/v1",
        fallback_capabilities=frozenset({"chat"}),
    )
    result = ModelRouter(
        {"tutor": config}, transport=httpx.MockTransport(handler)
    ).complete("tutor", [ModelMessage("user", "question")])

    assert result.text == "fallback output"
    assert result.used_fallback
    assert calls == [
        "https://cloud.test/v1/chat/completions",
        "http://local.test/v1/chat/completions",
    ]


def test_configured_task_specific_api_key_is_not_in_status_or_repr() -> None:
    secret = "task-specific-secret"
    config = load_task_config(
        "tutor",
        {
            "NEXUS_TUTOR_ENABLED": "true",
            "NEXUS_TUTOR_PROVIDER": "openai_compatible",
            "NEXUS_TUTOR_MODEL": "custom-model",
            "NEXUS_TUTOR_BASE_URL": "http://127.0.0.1:9000/v1",
            "NEXUS_TUTOR_API_KEY": secret,
        },
    )
    router = ModelRouter({"tutor": config})

    assert config.enabled
    assert config.api_key == secret
    assert secret not in repr(config)
    assert secret not in repr(router.status())


@pytest.mark.anyio
async def test_grounded_qa_routes_selected_evidence_and_validates_model_citations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "routed-qa.sqlite3"
    monkeypatch.setenv("NEXUS_DATABASE_PATH", str(database_path))
    from app.storage import save_document

    document_id = save_document(
        database_path,
        "synthetic.txt",
        "text/plain",
        [
            ExtractedRecord("page", 1, "An ammeter measures circuit current.", {"is_empty": False, "text_length": 36}),
            ExtractedRecord("page", 2, "A capacitor stores electric charge.", {"is_empty": False, "text_length": 34}),
        ],
    )
    with sqlite3.connect(database_path) as connection:
        source_id = connection.execute(
            "SELECT id FROM source_records WHERE document_id = ? AND source_number = 1",
            (document_id,),
        ).fetchone()[0]

    seen_evidence: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        user_content = json.loads(payload["messages"][1]["content"])
        seen_evidence.extend(user_content["evidence"])
        response_data = {
            "answer": "An ammeter measures circuit current.",
            "abstained": False,
            "abstention_reason": None,
            "citation_record_ids": [source_id],
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(response_data)}}]},
        )

    config = TaskModelConfig(
        task="tutor",
        enabled=True,
        provider="openai_compatible",
        model="mock-model",
        base_url="http://mock/v1",
        capabilities=frozenset({"chat"}),
    )
    router = ModelRouter({"tutor": config}, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(documents, "ANSWERER", RoutedEvidenceAnswerer(router))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/documents/{document_id}/ask",
            json={"question": "What measures current?"},
        )

    assert response.status_code == 200
    result = response.json()
    assert result["abstained"] is False
    assert result["citations"][0]["source_record_id"] == source_id
    assert result["citations"][0]["page_or_slide_number"] == 1
    assert len(seen_evidence) == 1
    assert seen_evidence[0]["source_record_id"] == source_id
    assert "capacitor" not in json.dumps(seen_evidence).casefold()


@pytest.mark.anyio
async def test_model_generated_invalid_citation_uses_deterministic_safe_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "invalid-citation.sqlite3"
    monkeypatch.setenv("NEXUS_DATABASE_PATH", str(database_path))
    from app.storage import save_document

    document_id = save_document(
        database_path,
        "synthetic.txt",
        "text/plain",
        [ExtractedRecord("page", 2, "Voltage is potential difference.", {"is_empty": False, "text_length": 31})],
    )

    def forged_handler(_: httpx.Request) -> httpx.Response:
        body = {
            "answer": "Forged source answer.",
            "abstained": False,
            "abstention_reason": None,
            "citation_record_ids": ["forged-id"],
        }
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(body)}}]})

    router = ModelRouter(
        {
            "tutor": TaskModelConfig(
                task="tutor",
                enabled=True,
                provider="openai_compatible",
                model="mock-model",
                base_url="http://mock/v1",
                capabilities=frozenset({"chat"}),
            )
        },
        transport=httpx.MockTransport(forged_handler),
    )
    monkeypatch.setattr(documents, "ANSWERER", RoutedEvidenceAnswerer(router))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/documents/{document_id}/ask",
            json={"question": "What is voltage?"},
        )

    assert response.status_code == 200
    result = response.json()
    assert result["answer"].startswith("The document states:")
    assert result["citations"][0]["page_or_slide_number"] == 2


@pytest.mark.anyio
async def test_model_status_is_secret_free_and_shows_disabled_defaults() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/models/status")

    assert response.status_code == 200
    assert len(response.json()["tasks"]) == 6
    assert all(task["enabled"] is False for task in response.json()["tasks"])
    assert "API_KEY" not in response.text
    assert "api_key" not in response.text


def test_smoke_refuses_missing_configuration_without_network_or_secret_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    router = ModelRouter(transport=httpx.MockTransport(handler))

    exit_code = run_smoke(router)
    output = capsys.readouterr().out

    assert exit_code != 0
    assert '"status": "not_configured"' in output
    assert calls == 0
    assert "API_KEY" not in output


def test_smoke_refuses_implicit_fallback_and_other_enabled_tasks(
    capsys: pytest.CaptureFixture[str],
) -> None:
    tutor = TaskModelConfig(
        task="tutor",
        enabled=True,
        provider="groq",
        model="operator-model",
        api_key="mock-key",
        fallback_provider="openai_compatible",
        fallback_model="local-model",
        fallback_base_url="http://127.0.0.1:11434/v1",
    )
    router = ModelRouter({"tutor": tutor})

    assert run_smoke(router) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "fallback_configured"
    assert result["provider"] == "groq"
    assert "mock-key" not in json.dumps(result)


def test_smoke_distinguishes_invalid_key_without_printing_response_body(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="provider says do not print this secret")

    router = ModelRouter(
        {
            "tutor": TaskModelConfig(
                task="tutor",
                enabled=True,
                provider="groq",
                model="operator-selected-model",
                api_key="mock-key",
            )
        },
        transport=httpx.MockTransport(handler),
        timeout_seconds=2.0,
        max_retries=0,
    )

    assert run_smoke(router) == 4
    output = capsys.readouterr().out
    assert '"status": "invalid_key"' in output
    assert "provider says" not in output
    assert "mock-key" not in output


def test_routed_answerer_uses_deterministic_fallback_for_malformed_json() -> None:
    from app.retrieval import SearchMatch

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not valid JSON"}}]},
        )

    router = ModelRouter(
        {
            "tutor": TaskModelConfig(
                task="tutor",
                enabled=True,
                provider="openai_compatible",
                model="mock-model",
                base_url="http://mock/v1",
            )
        },
        transport=httpx.MockTransport(handler),
    )
    evidence = [
        SearchMatch(
            document_id="document-id",
            source_record_id="persisted-source-id",
            source_type="pdf_page",
            page_or_slide_number=2,
            excerpt="Voltage measures potential difference.",
            score=1.0,
        )
    ]

    answer = RoutedEvidenceAnswerer(router).answer("What is voltage?", evidence)

    assert answer.citation_record_ids == ("persisted-source-id",)
    assert answer.answer.startswith("The document states:")


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [(429, ModelRateLimitError), (503, ModelUnavailableError), (400, ModelUnavailableError)],
)
def test_provider_http_failures_are_sanitized(
    status_code: int,
    expected_error: type[Exception],
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="secret-token-and-private-provider-detail")

    router = _router(
        "openai_compatible",
        "model",
        base_url="http://mock/v1",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(expected_error) as exc_info:
        router.complete("tutor", [ModelMessage("user", "test")])
    assert "secret-token" not in str(exc_info.value)
    assert "private-provider-detail" not in str(exc_info.value)


def test_timeout_is_sanitized_and_retried_only_to_configured_maximum() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("sensitive connection detail")

    router = _router(
        "openai_compatible",
        "model",
        base_url="http://mock/v1",
        transport=httpx.MockTransport(handler),
        max_retries=2,
    )
    with pytest.raises(ModelTimeoutError) as exc_info:
        router.complete("tutor", [ModelMessage("user", "test")])
    assert calls == 3
    assert "sensitive connection detail" not in str(exc_info.value)
    assert safe_diagnostic_text(exc_info.value) == "Configured provider request timed out."


def test_missing_credentials_and_capability_are_reported_without_calling_provider() -> None:
    config = TaskModelConfig(
        task="vision",
        enabled=True,
        provider="gemini",
        model="vision-model",
        capabilities=frozenset({"chat"}),
    )
    router = ModelRouter({"vision": config})
    with pytest.raises(ModelCapabilityError):
        router.complete(
            "vision",
            [ModelMessage("user", "describe image")],
            required_capabilities=frozenset({"vision"}),
        )

    chat_config = TaskModelConfig(
        task="tutor",
        enabled=True,
        provider="gemini",
        model="model",
    )
    with pytest.raises(ModelCredentialsError):
        ModelRouter({"tutor": chat_config}).complete(
            "tutor", [ModelMessage("user", "test")]
        )


def test_malformed_provider_output_is_rejected() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    router = _router(
        "openai_compatible",
        "model",
        base_url="http://mock/v1",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ModelOutputError):
        router.complete("tutor", [ModelMessage("user", "test")])


def test_disabled_provider_does_not_fall_back_implicitly() -> None:
    router = ModelRouter(
        {
            "tutor": TaskModelConfig(
                task="tutor", enabled=False, provider="disabled", model=""
            )
        }
    )
    with pytest.raises(ModelDisabledError):
        router.complete("tutor", [ModelMessage("user", "test")])