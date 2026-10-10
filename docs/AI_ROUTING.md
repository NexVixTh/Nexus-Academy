# AI Routing

NEXUS ACADEMY uses a small `httpx`-based provider adapter layer in `backend/app/model_routing.py`. No vendor SDK, LiteLLM, model, or cloud call is required. All task routes are disabled by default. Existing behavior remains available without credentials: tutor Q&A uses the deterministic quoted-evidence answerer, quiz generation stays deterministic, source-term labels remain extractive, and embeddings/vision are not invoked automatically.

## Configure a task

Copy `.env.example` values into the backend process environment (or use a local environment-file loader of your choice). The application does not parse `.env` files itself. Never commit `.env` or put provider credentials into frontend variables.

Every task has independent `ENABLED`, `PROVIDER`, `MODEL`, optional `BASE_URL`, `CAPABILITIES`, optional `MAX_TOKENS`, and optional fallback provider/model settings:

- `TUTOR`: grounded answer generation. This is the only provider task connected to a current user-facing model call.
- `QUIZ`: reserved configuration; quiz generation currently remains deterministic and server-owned.
- `CONCEPT`: reserved configuration for future concept/prerequisite extraction.
- `VISION`: capability-checked image request interface; no uploaded assets are automatically sent to a model.
- `EMBEDDING`: capability-checked text embedding interface; semantic retrieval is not enabled.
- `VERIFICATION`: reserved configuration for independent answer verification.

Model IDs are deliberately supplied by the operator; the project does not designate a permanent best model. The API's `GET /models/status` endpoint reports task, enabled state, provider/model IDs, declared capabilities, and configured fallback IDs only. It never reports credential values.

Example task selection (set these in the backend environment, not the frontend):

```text
NEXUS_TUTOR_ENABLED=true
NEXUS_TUTOR_PROVIDER=groq
NEXUS_TUTOR_MODEL=<provider-model-id>
NEXUS_TUTOR_MAX_TOKENS=700
GROQ_API_KEY=<secret>
```

To route quiz requests independently, configure `NEXUS_QUIZ_PROVIDER`, `NEXUS_QUIZ_MODEL`, and `NEXUS_QUIZ_ENABLED`; the present quiz API intentionally continues using its deterministic generator and does not call this task yet. The same separation applies to concept extraction and verification.

## Providers

- **Groq:** OpenAI-compatible chat endpoint. Set `NEXUS_<TASK>_PROVIDER=groq`, choose a current model ID, and set `GROQ_API_KEY`.
- **OpenRouter:** OpenAI-compatible chat endpoint. Set provider to `openrouter`, choose a model ID, and set `OPENROUTER_API_KEY`.
- **Google Gemini API:** Native `generateContent` adapter. Set provider to `gemini`, choose a model ID, and set `GEMINI_API_KEY`.
- **OpenAI-compatible endpoint:** Set provider to `openai_compatible`, choose a model ID, and set `NEXUS_<TASK>_BASE_URL`. An API key is optional for local endpoints; if needed, use `NEXUS_<TASK>_API_KEY` or `OPENAI_API_KEY`.
- **Local Ollama:** Use provider `openai_compatible`, a model ID served by the local Ollama instance, and a local OpenAI-compatible base URL such as `http://127.0.0.1:11434/v1`. No cloud provider is selected as an implicit fallback.

Provider/model availability and modality support depend on the operator's account, endpoint, and chosen model. Live provider access has not been validated with credentials in this project.

## Capabilities, retries, and limits

Chat is the default declared capability. Vision and embedding calls are refused unless `vision` or `embeddings` is explicitly listed in that task's `CAPABILITIES`. Current adapters implement mocked/tested OpenAI-compatible and Gemini request formats, but no application workflow automatically uses them. Declaring a capability is the operator's assertion that the selected model supports it; it is not a semantic understanding guarantee.

`NEXUS_MODEL_TIMEOUT_SECONDS` defaults to 20 seconds and is clamped to 0.1–300 seconds. `NEXUS_MODEL_MAX_RETRIES` defaults to 0 and is clamped to 0–5. Retries apply to timeout, rate-limit, and unavailable-server failures. Fallback happens only when both fallback provider and fallback model are explicitly configured. There is no automatic paid-provider switching. Per-task `MAX_TOKENS` limits generated output where supported; token limits are request safeguards, not a universal monetary budget. Provider billing/quotas remain provider-specific.

When cloud tutor routing is enabled, the provider receives the question and only the selected retrieved excerpts, source IDs, and locations included in the request. It does not receive the whole uploaded file or database. Cloud providers process those submitted prompts/evidence under their own terms; choose a local compatible endpoint when local-only processing is required.

Retrieved content is marked as untrusted in the system prompt. The server accepts citation IDs only if they refer to retrieved evidence and then validates them against persisted source records and exact page/slide provenance. Invalid, malformed, unavailable, or credential-less model responses fall back to the existing deterministic quoted-evidence answerer. That fallback is conservative but is not a fluent generative answer.
