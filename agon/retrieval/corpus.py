"""Corpus + qrels loaders with deterministic content-addressed versioning."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from agon.retrieval.interface import Corpus, Document, RetrievalCase, RetrievalDataset

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokenizer shared by lexical retrievers + tests."""
    return _TOKEN.findall(text.lower())


def _read(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        return yaml.safe_load(text)
    if path.suffix.lower() == ".json":
        return json.loads(text)
    raise ValueError(f"Unsupported file format: {path.suffix} ({path})")


def _corpus_version(documents: list[Document]) -> str:
    ordered = sorted(documents, key=lambda d: d.doc_id)
    payload = [{"doc_id": d.doc_id, "text": d.text} for d in ordered]
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_corpus(path: str | Path) -> Corpus:
    """Load a corpus file: a list of {doc_id, text} or {name, documents: [...]}."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Corpus not found: {path}")
    data = _read(path)
    if isinstance(data, list):
        name, records = path.stem, data
    elif isinstance(data, dict):
        name = data.get("name", path.stem)
        records = data.get("documents", [])
    else:
        raise ValueError(f"Unrecognized corpus structure in {path}")
    documents = [Document.model_validate(r) for r in records]
    return Corpus(name=name, corpus_version=_corpus_version(documents), documents=documents)


def _dataset_version(cases: list[RetrievalCase]) -> str:
    ordered = sorted(cases, key=lambda c: c.query_id)
    payload = [c.model_dump(mode="json") for c in ordered]
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_retrieval_dataset(path: str | Path) -> RetrievalDataset:
    """Load a qrels file: {name, cases: [{query_id, query, relevant_doc_ids, ...}]}."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Retrieval dataset not found: {path}")
    data = _read(path)
    if isinstance(data, list):
        name, records = path.stem, data
    elif isinstance(data, dict):
        name = data.get("name", path.stem)
        records = data.get("cases", [])
    else:
        raise ValueError(f"Unrecognized retrieval dataset structure in {path}")
    cases = [RetrievalCase.model_validate(r) for r in records]
    return RetrievalDataset(name=name, dataset_version=_dataset_version(cases), cases=cases)
