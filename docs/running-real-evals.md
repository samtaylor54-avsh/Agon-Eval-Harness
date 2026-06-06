# Running a real eval (providers, resilience, cost)

`agon` runs **offline by default** (`mockllm`, no API key). To run against a real provider:

## 1. Pick a provider + set its key

Keys come from the provider's own environment variables (e.g. `ANTHROPIC_API_KEY`,
`OPENAI_API_KEY`). `agon` does not store secrets.

```bash
export ANTHROPIC_API_KEY=sk-...            # your shell; never commit this
uv sync --extra providers                  # install the provider SDKs
uv run agon run examples/datasets/rag_smoke.yaml --model anthropic/claude-sonnet-4-5
```

`--model <provider>/<model>` switches the SUT adapter from `mockllm` to `litellm` automatically.

## 2. Tune resilience (all optional; sensible defaults)

| Flag | Meaning | Default |
|---|---|---|
| `--max-retries N` | retries per model request | 5 |
| `--request-timeout S` | whole-request timeout (s) | provider default |
| `--attempt-timeout S` | per-attempt timeout (s) | provider default |
| `--retry-on-error N` | retries for a whole failed sample | 0 |
| `--sample-time-limit S` | per-sample wall-clock cap (s) | none |
| `--fail-on-error V` | `true`/`false`, or an error-rate threshold `0..1` | false |

Example -- bound a flaky run and tolerate up to 10% sample errors:

```bash
uv run agon run suite.yaml --model anthropic/claude-sonnet-4-5 \
  --max-retries 3 --sample-time-limit 120 --fail-on-error 0.1
```

## 3. Read the cost

Every report includes a **Cost & usage** section (md + json) with input/output/total tokens and an
estimated USD cost, stamped `as of <date>`. Prices are an advisory, point-in-time snapshot
(`agon/cost/prices.py`) -- treat the figure as an estimate, not a bill. Offline `mockllm` runs report
their synthetic tokens at `$0.0000` (mock providers are priced as free).
