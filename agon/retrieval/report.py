"""Retrieval report — kept separate from generation reports (the isolation rule)."""

from __future__ import annotations

import json
from pathlib import Path

from inspect_ai.log import EvalLog

from agon.secrets import redact

METRICS = ["recall", "precision", "mrr", "ndcg", "hit"]


def retrieval_digest(log: EvalLog) -> dict:
    """Per-query metric rows + aggregate means from a retrieval EvalLog."""
    records: list[dict] = []
    for sample in log.samples or []:
        score = (sample.scores or {}).get("ir_scorer")
        if score is None:
            continue
        value = score.value if isinstance(score.value, dict) else {}
        meta = score.metadata or {}
        records.append(
            {
                "query_id": str(sample.id),
                **{m: float(value.get(m, 0.0)) for m in METRICS},
                "retrieved": meta.get("retrieved", []),
                "gold": meta.get("gold", []),
            }
        )
    n = len(records)
    means = {m: (sum(r[m] for r in records) / n if n else 0.0) for m in METRICS}
    meta = log.eval.metadata or {}
    return {
        "task": log.eval.task,
        "retriever": meta.get("retriever", "?"),
        "k": meta.get("k"),
        "corpus_version": meta.get("corpus_version", ""),
        "dataset_version": meta.get("dataset_version", ""),
        "n": n,
        "means": means,
        "records": records,
    }


def render_retrieval_markdown(digest: dict) -> str:
    m = digest["means"]
    k = digest["k"]
    lines = [
        f"# Retrieval Report — {digest['task']}",
        "",
        f"Retriever: `{digest['retriever']}` · k={k} · queries={digest['n']} · "
        f"corpus `{digest['corpus_version'][:12]}`",
        "",
        "## Aggregate (retrieval only — isolated from generation)",
        "",
        "| Metric | Mean |",
        "|---|---|",
        f"| recall@{k} | {m['recall']:.3f} |",
        f"| precision@{k} | {m['precision']:.3f} |",
        f"| MRR | {m['mrr']:.3f} |",
        f"| nDCG@{k} | {m['ndcg']:.3f} |",
        f"| hit@{k} | {m['hit']:.3f} |",
        "",
        "## Per query",
        "",
        f"| Query | recall@{k} | MRR | nDCG@{k} | hit |",
        "|---|---|---|---|---|",
    ]
    for r in digest["records"]:
        lines.append(
            f"| {r['query_id']} | {r['recall']:.2f} | {r['mrr']:.2f} | "
            f"{r['ndcg']:.2f} | {r['hit']:.0f} |"
        )
    return "\n".join(lines) + "\n"


def generate_retrieval_reports(log: EvalLog, *, out_dir: str | Path | None = None) -> dict:
    digest = retrieval_digest(log)
    artifacts = {
        "retrieval.md": render_retrieval_markdown(digest),
        "retrieval.json": json.dumps(digest, indent=2),
    }
    # Defense-in-depth: no secret value reaches a written/returned artifact.
    artifacts = {name: redact(content) for name, content in artifacts.items()}
    written: dict[str, str] = {}
    if out_dir is not None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        run_id = log.eval.run_id
        for name, content in artifacts.items():
            path = out / f"{run_id}.{name}"
            path.write_text(content, encoding="utf-8")
            written[name] = str(path)
    return {"digest": digest, "artifacts": artifacts, "written": written}
