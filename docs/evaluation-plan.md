# Phase 15 Evaluation Plan

## Asset batch boundary

This batch adds an independent CUAD v1 asset and does not complete Phase 15.
It does not change production APIs, ORM models, migrations, frontend behavior,
or the Phase 15 acceptance thresholds.

The fixed source is the Contract Understanding Atticus Dataset v1 from
repository commit `67faa0e6023b04fcaae6cc09497ab00e5d63a2a2`. The archive Git
blob SHA is `1ae94ff0a9b70b2e3b9b8d215737c8bfae460ddc`; the downloaded archive
SHA-256 is
`f8161d18bea4e9c05e78fa6dda61c19c846fb8087ea969c172753bc2f45b999a`.
The dataset is English, licensed CC BY 4.0, and identified by DOI
`10.5281/zenodo.4595826`. Attribution and the no-code-copy boundary are in
`evaluation/attribution/CUAD.md`.

The archive's verified structure is:

| Split | File | Contracts | Samples | Answer samples | No-answer samples | Categories |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| test | `test.json` | 102 | 4,182 | 1,244 | 2,938 | 41 |
| train | `train_separate_questions.json` | 408 | 22,450 | 11,180 | 11,270 | 41 |

The adapter extracts the category from CUAD's official question shape,
preserves document/question IDs, context, answer text, and offsets, and
rejects offset mismatches, duplicate IDs, malformed JSON, and cross-split
contract reuse. The official test file is not modified.

The verified category count is 41 in both splits. All 41 categories are
official CUAD question categories; the adapter does not add a `no_answer`,
`other`, or summary category. No dataset or mapping change was made to resolve
the earlier documentation count of 42.

## Cost estimate

Using the fixed current prompt-size estimate (`4` characters/token, `700`
prompt overhead characters, `120` expected output tokens/request), the full
official test estimate is:

- 102 contracts
- 4,182 requests before retries/repair calls
- 49,985,087 input tokens
- 501,840 output tokens
- Monetary amount unavailable because `MODEL_COST_PER_1K_INPUT` and
  `MODEL_COST_PER_1K_OUTPUT` are not configured in the environment

The estimator accepts explicit rates and records the formula in its JSON
output. Retries, repair calls, provider failures, and tokenization variance
must be added to a separately approved budget before any complete run.

## Controlled Qwen smoke

The final controlled smoke (before the endpoint configuration correction)
used CUAD test data with one contract, five
different CUAD categories, and a hard maximum of five provider requests. The
run was recorded at:
`evaluation/outputs/20260821T080216Z-46197ad3/`.

- Historical provider/model: Qwen / `qwen3.8-max`
- Historical endpoint region: `dashscope.aliyuncs.com`
- Dataset SHA-256: `f8161d18bea4e9c05e78fa6dda61c19c846fb8087ea969c172753bc2f45b999a`
- Git commit: `db7c90dd22c926611bc0d48e661cac362b470708`
- Prompt/schema/mapping: `cuad-native-prompt-v1` / `cuad-evaluation-schema-v1` / `cuad-product-mapping-v1`
- Requests: 5; provider request IDs: 4
- Actual tokens: 11,710 input / 3,477 output
- Actual and estimated monetary cost: unavailable because no rates were configured
- Provider failure rate: 100% (5/5); timeout: 1; schema failures: 2; request budget exhaustion: 1
- Native micro/macro precision, recall, and F1: 0 because all samples were no-prediction failures

The first two endpoint attempts are also preserved as ignored output runs for
auditability. No full CUAD formal evaluation was started. The smoke failure is
not a Phase 15 pass/fail conclusion.

## Qwen configuration review

The QwenCloud quickstart and structured-output guide document the OpenAI-
compatible base URL
`https://dashscope-intl.aliyuncs.com/compatible-mode/v1`, model
`qwen3.8-max`, Bearer authentication, and `response_format` JSON Object mode.
JSON Object mode requires the prompt to contain the word `JSON`; the existing
Gateway prompt does. The existing Gateway also leaves `max_tokens` unset, as
recommended by the structured-output guide.

The repository `.env` already contained the documented base URL, but the
application Settings previously ignored `MODEL_BASE_URL` and the production
Worker/evaluation runner consequently fell back to the old
`dashscope.aliyuncs.com` endpoint. This batch now loads `MODEL_BASE_URL`,
passes it through Docker Compose and the Worker, and derives the documented
`/chat/completions` endpoint. The evaluation manifest records the actual
Gateway endpoint region. No additional real Qwen request was made after this
correction; the historical five-request smoke above remains the only real
smoke evidence in this batch.

## Interpretation boundary

CUAD is useful for English clause evidence extraction only and may be affected
by model pretraining contamination. Product projection is limited to the
explicit mapping and must not be read as a product total score. CUAD cannot
prove the six Chinese contract categories, all seven product fields, or the
Chinese preset-risk metrics. A Chinese, authorized, human-reviewed gold set
remains a necessary Phase 15 release criterion.

## DeepSeek provider configuration

The project default real provider is now DeepSeek `deepseek-v4-flash` with
`https://api.deepseek.com` as the base URL and
`https://api.deepseek.com/chat/completions` as the endpoint. Requests use
Bearer authentication, `thinking: {"type":"disabled"}`, JSON Object mode,
and the configured bounded `MODEL_MAX_TOKENS` value. Every capability prompt
contains `Return exactly one JSON object.`, the word `JSON`, and a schema
example. Qwen remains an explicit optional provider through the same factory.

This configuration change was implemented and tested offline, followed by one
controlled real DeepSeek smoke. The local `.env` is not rewritten; if it still
contains Qwen settings or a Qwen key, deployment must manually configure the
DeepSeek key and matching variables. API keys are not recorded in evaluation
output.

DeepSeek pricing is not embedded in business code. When explicit rates are
provided to the evaluator, it records the formula from input/output token
usage; otherwise monetary cost remains `Not Calculated - Pricing Not
Configured`.

## Controlled DeepSeek smoke

The controlled smoke used only the CUAD v1 `test` split, one contract, and 3
samples (`Document Name`, `Parties`, and `Agreement Date`). It used the hard
CLI budget `--max-requests 5`, with `max_retries=0` and the existing single
JSON-repair path. The run is recorded at
`evaluation/outputs/smoke-deepseek-intl-20260821T000000Z/`.

- Endpoint: `https://api.deepseek.com/chat/completions`
- Provider/model: DeepSeek / `deepseek-v4-flash`
- Dataset SHA-256: `f8161d18bea4e9c05e78fa6dda61c19c846fb8087ea969c172753bc2f45b999a`
- Git commit: `db7c90dd22c926611bc0d48e661cac362b470708`
- Requests: 5 of 5 allowed; 3 initial calls and 2 controlled repair calls; no transport retry
- Samples: 3 selected, 2 completed, 1 failed; provider failure rate 33.33%
- Token usage: 14,218 input / 339 output / 14,557 total
- Error: 1 final `MODEL_EVIDENCE_MISSING` schema/evidence failure; no authentication, DNS, TLS, 429, or 5xx error was observed
- Cost: `Not Calculated - Pricing Not Configured`
- Result: endpoint connectivity passed; structured-output smoke partially passed. Per-request latency and per-attempt JSON/schema counters are not persisted by the current CLI; the manifest records aggregate run timestamps and request IDs.

This smoke is not a complete CUAD evaluation and is not a Phase 15 pass/fail
decision. The smoke report intentionally excludes contract context and raw
model responses.

## Next gate

Before a complete CUAD test run, a separate confirmation must set a request
budget and provider price rates, review the prompt/schema, and approve the
expected spend. The formal Phase 15 regression, security, performance,
Migration, E2E, and Chinese product evaluation gates remain open.
