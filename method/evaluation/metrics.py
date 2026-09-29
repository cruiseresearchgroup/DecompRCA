"""Evaluation metrics — top@k, Avg@k, and the retrieval–reranking decomposition.

  top@k         — 1 if any ground-truth root cause appears in the top-k predictions.
  Avg@k         — mean over (1..k) of top@j; the area under the top-k curve.
  Retrieval@K   — fraction of scenarios whose ground-truth cause is inside the
                  candidate set C of size K (argument `n_candidates`).
  Rerank@k      — among scenarios where the cause is inside C, the fraction in
                  which it is ranked among the first k (argument `cutoff`, k <= K).

By construction, top@k = Retrieval@K x Rerank@k, so
  retrieval failure = 1 - Retrieval@K
  reranking failure = Retrieval@K - top@k

Retrieval@K and Rerank@k apply to any method that outputs a ranking: by default
C is the first K items of the method's final ranking, so Retrieval@K = top@K and
Rerank@k = top@k / top@K. For a method with an explicit candidate set of its
own (e.g. the nodes kept by a learned causal graph), pass it as
`candidates_list`; a hit then requires the cause to be both among the first k
and inside that set, so the identity always holds.

All functions compare item identifiers as given and use rankings as given
(the paper's scoring); deduplicate a ranking beforehand if it may repeat items.
For service-level scoring (RCAEval), map predictions to services first.
"""

import numpy as np


def top_at_k(y_true: list[str], y_pred: list[str], k: int) -> int:
    """top@k — 1 if any ground-truth item appears in the top-k predictions."""
    if isinstance(y_true, str):
        raise TypeError("y_true must be a list of causes, not a string")
    return int(any(t in y_pred[:k] for t in y_true))


def avg_at_k(
    y_true_list: list[list[str]],
    y_pred_list: list[list[str]],
    k: int,
) -> float:
    """Avg@k — mean over scenarios of sum(top@1 .. top@k) / k (NaN if empty)."""
    scores = []
    for y_true, y_pred in zip(y_true_list, y_pred_list):
        scores.append(sum(top_at_k(y_true, y_pred, j) for j in range(1, k + 1)) / k)
    return float(np.mean(scores)) if scores else float("nan")


def _check(y_true_list, y_pred_list, candidates_list, cutoff=1, n_candidates=1):
    if cutoff < 1 or n_candidates < 1:
        raise ValueError(f"cutoff and n_candidates must be >= 1 "
                         f"(got cutoff={cutoff}, n_candidates={n_candidates})")
    if cutoff > n_candidates:
        raise ValueError(f"cutoff must be <= n_candidates "
                         f"(got cutoff={cutoff}, n_candidates={n_candidates})")
    if any(isinstance(t, str) for t in y_true_list):
        raise TypeError("y_true_list must hold a list of causes per scenario, not a string")
    if len(y_true_list) != len(y_pred_list):
        raise ValueError("y_true_list and y_pred_list differ in length")
    if candidates_list is not None and len(candidates_list) != len(y_true_list):
        raise ValueError("candidates_list and y_true_list differ in length")
    if candidates_list is not None and any(len(c) > n_candidates for c in candidates_list):
        raise ValueError(f"a candidate set is larger than n_candidates={n_candidates}")
    return candidates_list if candidates_list is not None else [None] * len(y_true_list)


def _in_candidates(y_true, y_pred, n_candidates, candidates):
    pool = candidates if candidates is not None else y_pred[:n_candidates]
    return int(any(t in pool for t in y_true))


def _hit_in_candidates(y_true, y_pred, cutoff, n_candidates, candidates):
    """Cause ranked among the first `cutoff` items AND inside the candidate set."""
    head = y_pred[:cutoff]
    pool = candidates if candidates is not None else y_pred[:n_candidates]
    return int(any(t in head and t in pool for t in y_true))


def retrieval_at_k(
    y_true_list: list[list[str]],
    y_pred_list: list[list[str]],
    n_candidates: int,
    candidates_list: list[list[str]] | None = None,
) -> float:
    """Retrieval@K with K = n_candidates — fraction of scenarios whose cause is
    in the candidate set.

    The candidate set defaults to the first `n_candidates` items of each
    ranking; pass `candidates_list` to use a method's own explicit candidate
    sets instead.
    """
    cands = _check(y_true_list, y_pred_list, candidates_list, n_candidates=n_candidates)
    hits = [
        _in_candidates(t, p, n_candidates, c)
        for t, p, c in zip(y_true_list, y_pred_list, cands)
    ]
    return float(np.mean(hits)) if hits else float("nan")


def rerank_at_k(
    y_true_list: list[list[str]],
    y_pred_list: list[list[str]],
    cutoff: int,
    n_candidates: int,
    candidates_list: list[list[str]] | None = None,
) -> float:
    """Rerank@k with k = cutoff — among scenarios whose cause is in the
    candidate set (of size K = n_candidates), the fraction in which it is
    ranked among the first `cutoff` items. Returns NaN when no scenario's
    cause is in the candidate set.
    """
    cands = _check(y_true_list, y_pred_list, candidates_list, cutoff, n_candidates)
    retrieved = hit = 0
    for t, p, c in zip(y_true_list, y_pred_list, cands):
        if _in_candidates(t, p, n_candidates, c):
            retrieved += 1
            hit += _hit_in_candidates(t, p, cutoff, n_candidates, c)
    return hit / retrieved if retrieved else float("nan")


def decompose(
    y_true_list: list[list[str]],
    y_pred_list: list[list[str]],
    cutoff: int,
    n_candidates: int,
    candidates_list: list[list[str]] | None = None,
) -> dict[str, float]:
    """Full retrieval–reranking decomposition.

    `cutoff` is k (the ranking cutoff of top@k and Rerank@k); `n_candidates`
    is K (the candidate-set size of Retrieval@K), with cutoff <= n_candidates.
    """
    cands = _check(y_true_list, y_pred_list, candidates_list, cutoff, n_candidates)
    if not y_true_list:
        nan = float("nan")
        return {f"top@{cutoff}": nan, f"Retrieval@{n_candidates}": nan,
                f"Rerank@{cutoff}": nan, "retrieval_failure": nan, "reranking_failure": nan}
    top = float(np.mean([_hit_in_candidates(t, p, cutoff, n_candidates, c)
                         for t, p, c in zip(y_true_list, y_pred_list, cands)]))
    ret = retrieval_at_k(y_true_list, y_pred_list, n_candidates, candidates_list)
    return {
        f"top@{cutoff}": top,
        f"Retrieval@{n_candidates}": ret,
        f"Rerank@{cutoff}": rerank_at_k(y_true_list, y_pred_list, cutoff, n_candidates,
                                        candidates_list),
        "retrieval_failure": 1.0 - ret,
        "reranking_failure": ret - top,
    }
