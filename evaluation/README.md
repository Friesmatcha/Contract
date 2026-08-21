# Independent Evaluation Assets

This directory contains independent, non-production evaluation tooling for
Phase 15. It does not add a production API, database table, migration, or
frontend page.

## CUAD v1

The pinned source is the Contract Understanding Atticus Dataset (CUAD) v1:

- Repository: `https://github.com/The-Atticus-Project/cuad`
- Repository commit: `67faa0e6023b04fcaae6cc09497ab00e5d63a2a2`
- Archive Git blob SHA: `1ae94ff0a9b70b2e3b9b8d215737c8bfae460ddc`
- Downloaded archive SHA-256: `f8161d18bea4e9c05e78fa6dda61c19c846fb8087ea969c172753bc2f45b999a`
- License: CC BY 4.0
- DOI: `10.5281/zenodo.4595826`
- Language: English

The downloaded archive and extracted contracts are ignored by Git under
`evaluation/datasets/raw/`. Outputs are ignored under `evaluation/outputs/`.
See [attribution/CUAD.md](attribution/CUAD.md) for attribution and the
repository-code licensing boundary. This project independently implements
span matching and does not copy CUAD `evaluate.py`.

The verified archive contains `test.json` and
`train_separate_questions.json`. The test split has 102 contracts, 4,182
question samples, 1,244 answer-bearing samples, 2,938 no-answer samples, and
41 official clause categories. The training split has 408 contracts and 22,450
samples with the same 41 official clause categories. No internal `no_answer`,
`other`, or summary category is added. The
split validator checks contract-level isolation.

## Commands

```powershell
python evaluation/scripts/download_cuad.py
python evaluation/scripts/validate_dataset.py --dataset cuad-v1
python evaluation/scripts/validate_split_isolation.py --dataset cuad-v1
python evaluation/scripts/estimate_qwen_cost.py --dataset cuad-v1 --split test
python evaluation/scripts/evaluate.py `
  --dataset cuad-v1 `
  --split test `
  --mode cuad-native `
  --provider deepseek `
  --limit-contracts 5 `
  --max-requests 210
```

The `--max-requests` budget is mandatory for every real provider (DeepSeek or
Qwen). A complete official test run is intentionally not started by this
batch. Ordinary CI uses only the `cuad-mini` fixture and the Fake provider:

```powershell
python evaluation/scripts/validate_dataset.py --dataset cuad-mini
python evaluation/scripts/evaluate.py --dataset cuad-mini --split test --mode cuad-native --provider fake
```

The project default real provider is DeepSeek with `MODEL_NAME=deepseek-v4-flash`,
`MODEL_BASE_URL=https://api.deepseek.com`, `MODEL_MAX_TOKENS=2048`, and
`MODEL_THINKING_MODE=disabled`. The runner and Worker use the same provider
factory. DeepSeek sends a Bearer token to `/chat/completions`, uses
`response_format={"type":"json_object"}`, includes `JSON` and an example in
each capability prompt, and records token usage without hard-coding prices.
Qwen remains available when `MODEL_PROVIDER=qwen` and retains its documented
DashScope base URL behavior. The runner never prints the API key or full
request/response.

Each run writes `run-manifest.json`, `predictions.jsonl`, `metrics.json`,
`metrics.csv`, `errors.jsonl`, and `report.md`. Errors are counted as no
prediction and also reported as provider failure categories. Outputs do not
contain full context or raw model responses.

The controlled DeepSeek smoke on 2026-08-21 used 3 CUAD Test samples and a
5-request hard budget. It reached `https://api.deepseek.com/chat/completions`
with `deepseek-v4-flash`: 5 requests were used, 2 samples completed, and 1
sample failed final evidence validation (`MODEL_EVIDENCE_MISSING`). It is
endpoint and structured-output smoke evidence only; no complete CUAD run or
Phase 15 pass conclusion follows from it. The aggregate run is recorded under
`evaluation/outputs/smoke-deepseek-intl-20260821T000000Z/`.

## Modes and limits

`cuad-native` measures English clause/span extraction: per-category and
micro/macro precision, recall, F1, AUPR, Precision@80%/90% recall, no-answer
accuracy, and provider/JSON/schema failure counts. Matching uses NFKC/case and
whitespace normalization, punctuation normalization, token-set Jaccard, and
the fixed `Jaccard >= 0.5` threshold. The Parties compatibility rule is
implemented in `evaluation/metrics/span_matching.py`.

`cuad-product-projection` uses the explicit `exact`, `partial`, and
`unsupported` mapping in `mappings/cuad-product-mapping.yaml`. It reports only
metrics for mapped CUAD evidence. It never emits a product total F1, treats a
clause occurrence as a business risk, equates Governing Law with complete
dispute resolution, or treats CUAD as a Chinese contract-classification gold
set.

CUAD is an English public benchmark and may have large-model pretraining
contamination. It cannot prove the product's six Chinese contract categories,
seven complete product fields, or Chinese contract risk metrics. The Chinese
product gold set remains necessary for Phase 15's formal metrics.
