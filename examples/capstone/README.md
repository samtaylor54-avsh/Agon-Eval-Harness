# Capstone — the whole loop in one script

A single, fully-offline walkthrough of the Agon practitioner loop. Run it:

```bash
uv run python examples/capstone/capstone.py
```

It narrates four acts as it goes:

1. **Build & fail.** A 3-case suite (`dataset.yaml`) is run against a system under test
   (`ANSWERS_V1`) that has a planted bug: the high-risk emergency-leave answer is correct
   but omits its citation. Result: `2/3 -> FAIL`.
2. **Localize.** The harness names the failing case, its category, its risk, and the
   `missing_citation` label — the cause, before reading a trace.
3. **Fix & pass.** A one-line change (`ANSWERS_V2` adds the citation) → `3/3 -> PASS`.
   The fixed case is now a permanent regression guard.
4. **Regress & catch.** A later change (`ANSWERS_V3`) drops a figure from a case that used
   to pass; run against the fixed baseline, the gate reports `regression detected=True,
   new_failures=['cap_003']` and exits 1.

Two steps that can't run offline are pointed to at the end: calibrating an LLM judge against
human labels (`agon calibrate`, needs a real provider — Manual Ch 9) and exporting a run to a
dashboard (`agon trace`, whose `console` backend *does* run offline — Manual Ch 19).

Everything here uses only built-in scorers (`citation_check`, `keyword_containment`) and the
`callable` SUT adapter — no custom scorer, no `--plugin`, no API key.
