"""``agon`` command-line interface (PRD §26 Task 11).

Commands: ``run``, ``resume``, ``compare``, ``report``, ``review``, ``calibrate``.

Exit codes (CI gating):
  0 — pass gate (recommendation PASS and no regression)
  1 — fail gate (recommendation FAIL/INVESTIGATE or regression detected)
  2 — abort (config / dataset / health-check error)
"""

from __future__ import annotations

from datetime import UTC, datetime

import anyio
import typer
from pydantic import ValidationError

from agon.analysis import compare_runs, find_run
from agon.calibrate import load_calibration_set, run_calibration
from agon.config import load_env, load_run_config
from agon.dataset import DatasetValidationError, load_dataset
from agon.reporting import generate_reports
from agon.review import save_review
from agon.schemas import JudgeConfig, Recommendation, ReviewRecord, RunConfig
from agon.scoring import JudgeClient, default_registry
from agon.scoring.judge import JudgeParseError
from agon.scoring.plugins import PluginLoadError, load_plugins
from agon.secrets import missing_provider_keys, redact, secret_status
from agon.sut import health_check
from agon.task import run_eval

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Agon Eval Harness")

ABORT = 2
FAIL_GATE = 1
PASS_GATE = 0


@app.callback()
def _load_env_callback() -> None:
    """Load a .env at CLI entry so preflight/doctor see those keys."""
    load_env()


def _preflight(model: str | None, adapter: str) -> None:
    """Abort (exit 2) if a real-provider run is missing its required API key(s)."""
    missing = missing_provider_keys(model, adapter)
    if missing:
        provider = (model or "").split("/")[0]
        typer.echo(
            f"[abort] missing API key for provider '{provider}': {', '.join(missing)} "
            f"(set it in your shell or a .env file)",
            err=True,
        )
        raise typer.Exit(ABORT)


def _parse_fail_on_error(value: str) -> bool | float:
    low = value.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    return float(value)


def _apply_resilience_flags(
    cfg: RunConfig,
    *,
    max_retries: int | None = None,
    request_timeout: int | None = None,
    attempt_timeout: int | None = None,
    retry_on_error: int | None = None,
    sample_time_limit: int | None = None,
    fail_on_error: str | None = None,
) -> None:
    r = cfg.resilience
    if max_retries is not None:
        r.max_retries = max_retries
    if request_timeout is not None:
        r.request_timeout = request_timeout
    if attempt_timeout is not None:
        r.attempt_timeout = attempt_timeout
    if retry_on_error is not None:
        r.retry_on_error = retry_on_error
    if sample_time_limit is not None:
        r.sample_time_limit = sample_time_limit
    if fail_on_error is not None:
        r.fail_on_error = _parse_fail_on_error(fail_on_error)


def _validate_scorers(ds) -> list[str]:
    """Return the sorted scorer types referenced by the dataset that are not registered."""
    unknown = {
        spec.type
        for case in ds.test_cases
        for spec in case.scoring
        if not default_registry.has(spec.type)
    }
    return sorted(unknown)


@app.command()
def run(
    dataset: str = typer.Argument(..., help="Path to a dataset (.yaml/.json/.jsonl)"),
    config: str = typer.Option(None, "--config", "-c", help="Run config (.toml/.yaml/.json)"),
    system_version: str = typer.Option(None, "--system-version"),
    model: str = typer.Option(None, "--model", help="LiteLLM model string (implies litellm)"),
    adapter: str = typer.Option(None, "--adapter", help="mockllm|litellm|http"),
    epochs: int = typer.Option(None, "--epochs", help="Repetitions per case"),
    log_dir: str = typer.Option(None, "--log-dir"),
    report_dir: str = typer.Option(None, "--report-dir"),
    baseline: str = typer.Option(None, "--baseline", help="Baseline run_id for regression"),
    display: str = typer.Option("plain", "--display", help="Inspect display: plain|rich|none"),
    plugin: list[str] = typer.Option(  # noqa: B008
        [], "--plugin", "-p", help="Import a scorer module (dotted name or .py path) before running"
    ),
    max_retries: int = typer.Option(None, "--max-retries", help="Per-request retry count"),
    request_timeout: int = typer.Option(
        None, "--request-timeout", help="Whole-request timeout (s)"
    ),
    attempt_timeout: int = typer.Option(
        None, "--attempt-timeout", help="Per-attempt timeout (s)"
    ),
    retry_on_error: int = typer.Option(None, "--retry-on-error", help="Per-sample retry count"),
    sample_time_limit: int = typer.Option(
        None, "--sample-time-limit", help="Per-sample time limit (s)"
    ),
    fail_on_error: str = typer.Option(
        None, "--fail-on-error", help="true|false or error-rate 0..1"
    ),
) -> None:
    """Run an eval suite and emit Markdown/JSON/JUnit reports + a release recommendation."""
    cfg = load_run_config(config) if config else RunConfig()
    if system_version:
        cfg.system_version = system_version
    if adapter:
        cfg.sut.adapter = adapter
    if model:
        cfg.sut.model = model
        if not adapter and cfg.sut.adapter == "mockllm":
            cfg.sut.adapter = "litellm"
    if epochs:
        cfg.epochs = epochs
    if log_dir:
        cfg.log_dir = log_dir
    if report_dir:
        cfg.report_dir = report_dir
    if baseline:
        cfg.baseline_run = baseline

    try:
        _apply_resilience_flags(
            cfg,
            max_retries=max_retries,
            request_timeout=request_timeout,
            attempt_timeout=attempt_timeout,
            retry_on_error=retry_on_error,
            sample_time_limit=sample_time_limit,
            fail_on_error=fail_on_error,
        )
    except (ValueError, ValidationError) as exc:
        typer.echo(f"[abort] invalid resilience flag: {exc}", err=True)
        raise typer.Exit(ABORT) from exc

    try:
        loaded = load_plugins(plugin)
    except PluginLoadError as exc:
        typer.echo(f"[abort] {exc}", err=True)
        raise typer.Exit(ABORT) from exc
    if loaded:
        typer.echo(f"loaded plugin scorers: {', '.join(loaded)}")

    try:
        ds = load_dataset(dataset)
    except (DatasetValidationError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"[abort] {exc}", err=True)
        raise typer.Exit(ABORT) from exc

    unknown = _validate_scorers(ds)
    if unknown:
        typer.echo(
            f"[abort] unknown scorer_type(s): {', '.join(unknown)}; "
            f"registered: {', '.join(default_registry.keys())}; "
            f"did you forget --plugin <module-or-file>?",
            err=True,
        )
        raise typer.Exit(ABORT)

    _preflight(cfg.sut.model, cfg.sut.adapter)

    if not anyio.run(health_check, cfg.sut):
        typer.echo("[abort] SUT health check failed", err=True)
        raise typer.Exit(ABORT)

    log = run_eval(ds, cfg, display=display)
    baseline_log = find_run(cfg.log_dir, cfg.baseline_run) if cfg.baseline_run else None
    result = generate_reports(log, config=cfg, baseline_log=baseline_log, out_dir=cfg.report_dir)

    d = result["digest"]
    rec: Recommendation = result["recommendation"]
    regression = result["regression"]
    typer.echo(
        f"\n{ds.name}: pass {d.overall_pass_rate * 100:.1f}% "
        f"({sum(r.passed for r in d.records)}/{len(d.records)})  -> {rec.value}"
    )
    if regression is not None:
        typer.echo(
            f"regression vs {regression.baseline_run_id}: "
            f"{'DETECTED' if regression.regression_detected else 'none'} "
            f"(+{len(regression.new_failures)} new, -{len(regression.fixed_failures)} fixed)"
        )
    for path in result["written"].values():
        typer.echo(f"  wrote {path}")

    regressed = regression is not None and regression.regression_detected
    if rec is Recommendation.PASS and not regressed:
        raise typer.Exit(PASS_GATE)
    raise typer.Exit(FAIL_GATE)


@app.command()
def resume(
    run_id: str = typer.Argument(None, help="Run id to resume (default: latest in --log-dir)"),
    config: str = typer.Option(None, "--config", "-c", help="Run config (.toml/.yaml/.json)"),
    log_dir: str = typer.Option(None, "--log-dir"),
    report_dir: str = typer.Option(None, "--report-dir"),
    display: str = typer.Option("plain", "--display", help="Inspect display: plain|rich|none"),
    latest: bool = typer.Option(False, "--latest", help="Resume the most recent run"),
    plugin: list[str] = typer.Option(  # noqa: B008
        [], "--plugin", "-p", help="Import a scorer module (dotted name or .py path) before running"
    ),
    max_retries: int = typer.Option(None, "--max-retries", help="Per-request retry count"),
    request_timeout: int = typer.Option(
        None, "--request-timeout", help="Whole-request timeout (s)"
    ),
    attempt_timeout: int = typer.Option(
        None, "--attempt-timeout", help="Per-attempt timeout (s)"
    ),
    retry_on_error: int = typer.Option(None, "--retry-on-error", help="Per-sample retry count"),
    sample_time_limit: int = typer.Option(
        None, "--sample-time-limit", help="Per-sample time limit (s)"
    ),
    fail_on_error: str = typer.Option(
        None, "--fail-on-error", help="true|false or error-rate 0..1"
    ),
) -> None:
    """Re-run the failed/incomplete cases of a prior run and emit a merged report."""
    from agon.task.resume import resume_run

    cfg = load_run_config(config) if config else RunConfig()
    if log_dir:
        cfg.log_dir = log_dir
    if report_dir:
        cfg.report_dir = report_dir

    try:
        _apply_resilience_flags(
            cfg,
            max_retries=max_retries,
            request_timeout=request_timeout,
            attempt_timeout=attempt_timeout,
            retry_on_error=retry_on_error,
            sample_time_limit=sample_time_limit,
            fail_on_error=fail_on_error,
        )
    except (ValueError, ValidationError) as exc:
        typer.echo(f"[abort] invalid resilience flag: {exc}", err=True)
        raise typer.Exit(ABORT) from exc

    try:
        loaded = load_plugins(plugin)
    except PluginLoadError as exc:
        typer.echo(f"[abort] {exc}", err=True)
        raise typer.Exit(ABORT) from exc
    if loaded:
        typer.echo(f"loaded plugin scorers: {', '.join(loaded)}")

    if latest and run_id:
        typer.echo("[warn] both run_id and --latest given; using latest", err=True)
    target = None if latest else run_id
    _preflight(cfg.sut.model, cfg.sut.adapter)
    try:
        result = resume_run(cfg, target, display=display)
    except FileNotFoundError as exc:
        typer.echo(f"[abort] {exc}", err=True)
        raise typer.Exit(ABORT) from exc

    if result["resumed"] == 0:
        typer.echo("nothing to resume: all cases completed in the prior run")
        raise typer.Exit(PASS_GATE)

    d = result["digest"]
    rec: Recommendation = result["recommendation"]
    typer.echo(
        f"\nresumed {result['resumed']} case(s): pass {d.overall_pass_rate * 100:.1f}% "
        f"({sum(r.passed for r in d.records)}/{len(d.records)})  -> {rec.value}"
    )
    for path in result["written"].values():
        typer.echo(f"  wrote {path}")

    regression = result["regression"]
    regressed = regression is not None and regression.regression_detected
    if rec is Recommendation.PASS and not regressed:
        raise typer.Exit(PASS_GATE)
    raise typer.Exit(FAIL_GATE)


@app.command()
def compare(
    current: str = typer.Argument(..., help="Current run_id"),
    baseline: str = typer.Argument(..., help="Baseline run_id"),
    log_dir: str = typer.Option("logs", "--log-dir"),
) -> None:
    """Compare two runs and report regressions. Exit 1 if a regression is detected."""
    try:
        cur = find_run(log_dir, current)
        base = find_run(log_dir, baseline)
    except FileNotFoundError as exc:
        typer.echo(f"[abort] {exc}", err=True)
        raise typer.Exit(ABORT) from exc
    reg = compare_runs(cur, base)
    typer.echo(f"regression detected: {reg.regression_detected}")
    typer.echo(f"  new failures:   {', '.join(reg.new_failures) or 'none'}")
    typer.echo(f"  fixed failures: {', '.join(reg.fixed_failures) or 'none'}")
    t = reg.pass_rate_test
    if t is not None:
        note = "significant" if t.significant else "not significant"
        small = "; small sample" if reg.small_sample else ""
        typer.echo(
            f"  overall pass-rate diff: {t.diff * 100:+.1f}pp "
            f"(p={t.p_value:.3f}, {note}{small})"
        )
    for tid, old, new in reg.score_drops:
        typer.echo(f"  drop {tid}: {old:.2f} ->{new:.2f}")
    raise typer.Exit(FAIL_GATE if reg.regression_detected else PASS_GATE)


@app.command()
def report(
    run_id: str = typer.Argument(..., help="Run id to report on"),
    log_dir: str = typer.Option("logs", "--log-dir"),
    report_dir: str = typer.Option("reports", "--report-dir"),
    baseline: str = typer.Option(None, "--baseline"),
) -> None:
    """Regenerate reports for a stored run."""
    try:
        log = find_run(log_dir, run_id)
        baseline_log = find_run(log_dir, baseline) if baseline else None
    except FileNotFoundError as exc:
        typer.echo(f"[abort] {exc}", err=True)
        raise typer.Exit(ABORT) from exc
    result = generate_reports(
        log, config=RunConfig(), baseline_log=baseline_log, out_dir=report_dir
    )
    typer.echo(f"recommendation: {result['recommendation'].value}")
    for path in result["written"].values():
        typer.echo(f"  wrote {path}")


@app.command()
def doctor(
    model: str = typer.Option(None, "--model", help="Check keys for this provider/model"),
    config: str = typer.Option(None, "--config", "-c", help="Show resolved config (redacted)"),
) -> None:
    """Report agon/Inspect versions, masked secret status, and provider-key readiness."""
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version

    def _ver(name: str) -> str:
        try:
            return _pkg_version(name)
        except PackageNotFoundError:
            return "(unknown)"

    typer.echo("agon doctor")
    typer.echo(f"  agon:    {_ver('agon-eval-harness')}")
    typer.echo(f"  inspect: {_ver('inspect-ai')}")
    typer.echo("  default path: offline (mockllm; no API key required)")

    typer.echo("\nsecret env vars:")
    for var, shown in secret_status():
        typer.echo(f"  {var}: {shown}")

    if model:
        adapter = "mockllm" if model.startswith("mockllm") else "litellm"
        provider = model.split("/")[0]
        missing = missing_provider_keys(model, adapter)
        if missing:
            typer.echo(f"\nmodel {model}: provider '{provider}' MISSING {', '.join(missing)}")
        else:
            typer.echo(f"\nmodel {model}: provider '{provider}' keys present")

    if config:
        cfg = load_run_config(config)
        typer.echo("\nresolved config:")
        typer.echo(redact(cfg.model_dump_json(indent=2)))


@app.command()
def trace(
    run_id: str = typer.Argument(..., help="Run id to export as OpenTelemetry spans"),
    log_dir: str = typer.Option("logs", "--log-dir"),
    backend: str = typer.Option("console", "--backend", help="console | langsmith | otlp"),
    endpoint: str = typer.Option(None, "--endpoint", help="OTLP endpoint (otlp backend)"),
) -> None:
    """Export a stored run as OpenTelemetry GenAI spans (console offline / LangSmith / OTLP)."""
    try:
        from agon.observability import (
            console_tracer,
            export_eval_log,
            langsmith_tracer,
            otlp_tracer,
        )
    except ImportError as exc:
        typer.echo("[abort] observability needs the [otel] extra: uv sync --extra otel", err=True)
        raise typer.Exit(ABORT) from exc

    try:
        log = find_run(log_dir, run_id)
    except FileNotFoundError as exc:
        typer.echo(f"[abort] {exc}", err=True)
        raise typer.Exit(ABORT) from exc

    if backend == "console":
        tracer = console_tracer()
    elif backend == "langsmith":
        tracer = langsmith_tracer()
    elif backend == "otlp":
        if not endpoint:
            typer.echo("[abort] otlp backend requires --endpoint", err=True)
            raise typer.Exit(ABORT)
        tracer = otlp_tracer(endpoint)
    else:
        typer.echo(f"[abort] unknown backend {backend!r}", err=True)
        raise typer.Exit(ABORT)

    count = export_eval_log(log, tracer)
    typer.echo(f"exported {count} spans to {backend}")


@app.command()
def retrieve(
    corpus: str = typer.Argument(..., help="Corpus file (.yaml/.json): documents to search"),
    qrels: str = typer.Argument(..., help="Retrieval dataset (.yaml/.json): queries + gold IDs"),
    k: int = typer.Option(10, "--k", help="Top-k cutoff for the metrics"),
    retriever: str = typer.Option("bm25", "--retriever", help="bm25 | lancedb | hybrid"),
    log_dir: str = typer.Option("logs", "--log-dir"),
    report_dir: str = typer.Option("reports", "--report-dir"),
) -> None:
    """Run an isolated retrieval eval (recall@k / MRR / nDCG / hit@k) — no generation."""
    from agon.retrieval import (
        BM25Retriever,
        HybridRetriever,
        LanceDBRetriever,
        generate_retrieval_reports,
        load_corpus,
        load_retrieval_dataset,
        run_retrieval_eval,
    )

    try:
        corpus_obj = load_corpus(corpus)
        dataset = load_retrieval_dataset(qrels)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"[abort] {exc}", err=True)
        raise typer.Exit(ABORT) from exc

    if retriever == "bm25":
        impl = BM25Retriever()
    elif retriever == "lancedb":
        impl = LanceDBRetriever()  # default embedder needs the [semantic] extra
    elif retriever == "hybrid":
        impl = HybridRetriever(LanceDBRetriever(), BM25Retriever())
    else:
        typer.echo(f"[abort] unknown retriever {retriever!r}", err=True)
        raise typer.Exit(ABORT)

    log = run_retrieval_eval(corpus_obj, dataset, retriever=impl, k=k, log_dir=log_dir)
    result = generate_retrieval_reports(log, out_dir=report_dir)
    means = result["digest"]["means"]
    typer.echo(
        f"\n{dataset.name} [{retriever}]: recall@{k}={means['recall']:.3f} "
        f"MRR={means['mrr']:.3f} nDCG@{k}={means['ndcg']:.3f} hit@{k}={means['hit']:.3f}"
    )
    for path in result["written"].values():
        typer.echo(f"  wrote {path}")


@app.command()
def review(
    run_id: str = typer.Option(..., "--run-id"),
    test_id: str = typer.Option(..., "--test-id"),
    reviewer: str = typer.Option(..., "--reviewer"),
    notes: str = typer.Option("", "--notes"),
    override_passed: bool = typer.Option(None, "--override-passed/--override-failed"),
    ambiguous: bool = typer.Option(False, "--ambiguous"),
    reviews_dir: str = typer.Option("reviews", "--reviews-dir"),
) -> None:
    """Append a human review/override for a case (the eval log itself is never mutated)."""
    record = ReviewRecord(
        run_id=run_id,
        test_id=test_id,
        reviewer=reviewer,
        override_passed=override_passed,
        ambiguous=ambiguous,
        notes=notes,
        timestamp=datetime.now(UTC).isoformat(),
    )
    path = save_review(record, reviews_dir)
    typer.echo(f"recorded review for {test_id} ->{path}")


@app.command()
def calibrate(
    labeled: str = typer.Argument(..., help="Calibration set (.yaml) with human labels"),
    judge_model: str = typer.Option("mockllm/model", "--judge-model"),
    min_kappa: float = typer.Option(0.6, "--min-kappa", help="Minimum acceptable agreement"),
) -> None:
    """Validate a judge scorer against human labels. Exit 1 if agreement < min-kappa."""
    _preflight(judge_model, "mockllm" if judge_model.startswith("mockllm") else "litellm")
    try:
        cset = load_calibration_set(labeled)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"[abort] {exc}", err=True)
        raise typer.Exit(ABORT) from exc
    judge = JudgeClient(JudgeConfig(model=judge_model))
    try:
        report = anyio.run(lambda: run_calibration(cset, judge, min_kappa=min_kappa))
    except JudgeParseError as exc:
        typer.echo(
            f"[abort] judge '{judge_model}' returned unparseable output - calibration needs a "
            f"real judge model (e.g. --judge-model openai/gpt-4o). Details: {exc}",
            err=True,
        )
        raise typer.Exit(ABORT) from exc
    small = " (small sample)" if report.small_sample else ""
    typer.echo(
        f"calibration [{report.scorer_type}] n={report.n} "
        f"accuracy={report.accuracy:.2f} "
        f"kappa={report.cohen_kappa:.2f} [{report.kappa_ci.low:.2f}, {report.kappa_ci.high:.2f}] "
        f"(min {report.min_kappa}){small} -> {'PASS' if report.passed else 'FAIL'}"
    )
    for tid, human, judged in report.disagreements:
        typer.echo(f"  disagree {tid}: human={human} judge={judged}")
    raise typer.Exit(PASS_GATE if report.passed else FAIL_GATE)


if __name__ == "__main__":
    app()
