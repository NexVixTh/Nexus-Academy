from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.model_routing import (  # noqa: E402
    TASK_NAMES,
    ModelAuthenticationError,
    ModelCredentialsError,
    ModelDisabledError,
    ModelMessage,
    ModelNetworkError,
    ModelOutputError,
    ModelRateLimitError,
    ModelRouter,
    ModelTimeoutError,
    ModelUnavailableError,
)

CLOUD_PROVIDERS = {"groq", "openrouter", "gemini"}
SMOKE_PROMPT = "Reply with exactly: NEXUS_TUTOR_SMOKE_OK"


def main() -> int:
    router = ModelRouter(timeout_seconds=15.0, max_retries=0)
    return run_smoke(router)


def run_smoke(router: ModelRouter) -> int:
    configs = router.configs
    tutor = configs.get("tutor")
    if tutor is None or not tutor.enabled:
        return _report("not_configured", "Enable NEXUS_TUTOR and set provider/model first.", 2)
    if tutor.provider not in CLOUD_PROVIDERS:
        return _report("not_cloud_provider", "Smoke test accepts Groq, OpenRouter, or Gemini only.", 2)
    if tutor.fallback_configured:
        return _report(
            "fallback_configured",
            "Disable tutor fallback before the smoke test so only the selected cloud model is called.",
            2,
        )
    enabled_other_tasks = [
        task for task in TASK_NAMES if task != "tutor" and configs[task].enabled
    ]
    if enabled_other_tasks:
        return _report(
            "other_tasks_enabled",
            "Disable all non-tutor model tasks before the smoke test.",
            2,
        )

    started = time.perf_counter()
    try:
        router.complete(
            "tutor",
            [ModelMessage("user", SMOKE_PROMPT)],
        )
    except ModelCredentialsError:
        return _report("missing_key", "Required provider key is not present in the backend environment.", 3, tutor)
    except ModelAuthenticationError:
        return _report("invalid_key", "Provider rejected authentication; check key validity and account access.", 4, tutor)
    except ModelRateLimitError:
        return _report("rate_limited", "Provider returned a rate limit; no alternate provider was called.", 5, tutor)
    except ModelTimeoutError:
        return _report("timeout", "Configured provider request timed out.", 6, tutor)
    except ModelNetworkError:
        return _report("network_error", "Could not connect to the configured provider.", 7, tutor)
    except ModelUnavailableError:
        return _report("provider_unavailable", "Provider returned an unavailable/server response.", 8, tutor)
    except ModelOutputError:
        return _report("malformed_response", "Provider returned a malformed or empty response.", 9, tutor)
    except ModelDisabledError:
        return _report("not_configured", "Tutor model task is disabled or incomplete.", 2, tutor)

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    return _report(
        "success",
        "Configured tutor provider returned a non-empty response. Response content was not logged.",
        0,
        tutor,
        elapsed_ms,
    )


def _report(
    status: str,
    detail: str,
    exit_code: int,
    config: object | None = None,
    latency_ms: float | None = None,
) -> int:
    output: dict[str, object] = {"status": status, "detail": detail}
    if config is not None:
        output["provider"] = getattr(config, "provider", None)
        output["model"] = getattr(config, "model", None)
    if latency_ms is not None:
        output["latency_ms"] = latency_ms
    print(json.dumps(output, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
