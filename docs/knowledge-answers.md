# Knowledge answers

POST `/api/v1/knowledge/answers` accepts `question` and optional `limit` (default 5).
It calls existing Hybrid Search with the question, then keeps current confirmed real cases
whose similarity meets `AESTHETICLENS_ANSWER_MIN_SIMILARITY` (default 0.3).
This is an operational cosine threshold, not a calibrated relevance probability.

Context includes summary, style tags, current reviewed interpretations, and only resolved
numeric facts referenced by the case's evidence. Feature JSON and feedback comments are excluded.
The existing `AESTHETICLENS_PROVIDER=chat_completions`, `AESTHETICLENS_BASE_URL`,
`AESTHETICLENS_MODEL`, `AESTHETICLENS_API_KEY`, timeout and completion-token settings
configure answer generation. Existing embedding configuration supports retrieval.

Response fields: `status`, `answer`, `cited_case_ids` (analysis result UUIDs), and
`retrieved_cases` including similarity. Empty or below-threshold retrieval returns
`insufficient_evidence` without calling the LLM. The model may also decline evidence;
missing/out-of-context citations fail closed. Citation validation checks membership, not
semantic entailment of every generated claim. Provider failures return 502, missing provider
configuration returns 503. Answers are not persisted. No schema migration is needed.
