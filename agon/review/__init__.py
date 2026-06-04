"""Human review: append-only override/notes stored beside the immutable eval log.

Inspect's ``.eval`` logs are never mutated (architectural invariant). Human judgments are
appended as ``ReviewRecord`` rows in a sibling JSONL file, and traces are inspected with
``inspect view``.
"""

from agon.review.store import load_reviews, save_review

__all__ = ["load_reviews", "save_review"]
