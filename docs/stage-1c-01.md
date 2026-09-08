# Stage 1C-01

The existing service now injects an `AnalysisAdapter`: explicit `mock` or `chat_completions`. No public response fields, storage, feature algorithms, or routes changed. Real pixel features plus Mock semantics are `hybrid`; attempted real semantics are `real`, with `provenance.semantic.status` and overall partial status independently describing failure.

## Local setup

Copy `.env.example` to `.env`. Keep `AESTHETICLENS_PROVIDER=mock` for free offline operation. For live use, set it to `chat_completions`, and fill `AESTHETICLENS_BASE_URL` (API base ending in `/v1` where applicable), `AESTHETICLENS_MODEL` (a vision-capable model), and `AESTHETICLENS_API_KEY`. Values are backend-only except `NEXT_PUBLIC_AESTHETICLENS_API_URL`.

From `backend`, run `python -m uvicorn app.main:app --env-file ../.env --port 8000`; from the repository root, run `pnpm dev`. Uvicorn's existing standard dependencies support env-file loading. Merely editing `.env` without restarting/loading it does not configure the process.

HTTP transport reuses httpx and follows the image content format in the [official image-input documentation](https://developers.openai.com/api/docs/guides/images-vision). Providers must support inline PNG images, Chat Completions JSON mode and `max_completion_tokens`. No provider/model compatibility is claimed until live validation.

## Validation and provenance

Input is the normalized, orientation-corrected, alpha-composited sRGB raster plus successful feature leaf values. References use `feature:<extractor_code>#/JSON/pointer`, including escaped keys and array indices. The model sees the exact reference catalog, configured vocabulary and versioned Pydantic JSON Schema. Output must contain every configured dimension exactly once, only known style codes, and either validated evidence or explicit uncertainty for each dimension.

In prose, numeric facts use `{{feature:code#/path}}`; the server validates membership in that dimension's references then substitutes the actual value. Bare Arabic digits or malformed placeholders in prose are rejected. This protects referenced measurements; it cannot prove that every qualitative observation or number written in words is true. Human review and evaluation remain necessary. Confidence is retained for compatibility but never displayed as an accuracy probability.

Only timeouts, transport errors, HTTP 429 and server errors retry, up to configured `max_retries` (0–3). Invalid JSON, schema, references, refusals and truncated output fail without silent Mock fallback. Failed semantics preserve computed features and all five tabs, with explicit unavailable messages and a partial result. Missing or invalid live configuration behaves the same way.

The existing free-form `provenance.semantic` stores model, prompt/schema/vocabulary versions, duration, per-attempt known token usage and sanitized error codes. Cost stays null; usage missing from timed-out attempts is not guessed. Metadata is in the existing in-memory result repository and disappears on restart.

Offline tests replace HTTP transports and block real httpx transports; no API credentials or provider credits are needed. Live image validation remains pending until explicit provider/model/key configuration and authorization are available.
