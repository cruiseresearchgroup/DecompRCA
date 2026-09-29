"""Retrieval-reranking decomposition: README example, identity, argument checks."""

import math
import random

import pytest

from method.evaluation.metrics import avg_at_k, decompose, rerank_at_k, retrieval_at_k


def test_readme_example():
    y_true = [["P101"], ["FIT201"]]
    y_pred = [["LIT101", "P101", "MV101"], ["FIT201", "AIT202", "P201"]]
    assert decompose(y_true, y_pred, cutoff=1, n_candidates=15) == {
        "top@1": 0.5, "Retrieval@15": 1.0, "Rerank@1": 0.5,
        "retrieval_failure": 0.0, "reranking_failure": 0.5,
    }


def _random_case(seed, n=40, vocab=12, K=5, explicit=False):
    rng = random.Random(seed)
    items = [f"m{i}" for i in range(vocab)]
    y_true = [rng.sample(items, rng.randint(1, 2)) for _ in range(n)]
    y_pred = [rng.sample(items, vocab) for _ in range(n)]
    cands = [rng.sample(items, rng.randint(1, K)) for _ in range(n)] if explicit else None
    return y_true, y_pred, cands


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("seed", range(5))
@pytest.mark.parametrize("cutoff,K", [(1, 5), (3, 5), (5, 5)])
def test_top_equals_retrieval_times_rerank(seed, explicit, cutoff, K):
    y_true, y_pred, cands = _random_case(seed, K=K, explicit=explicit)
    d = decompose(y_true, y_pred, cutoff=cutoff, n_candidates=K, candidates_list=cands)
    ret = retrieval_at_k(y_true, y_pred, K, cands)
    rr = rerank_at_k(y_true, y_pred, cutoff, K, cands)
    assert d[f"Retrieval@{K}"] == ret and d[f"Rerank@{cutoff}"] == rr
    assert 0.0 < ret < 1.0          # both factors are exercised
    assert d[f"top@{cutoff}"] == pytest.approx(ret * rr)
    assert d["retrieval_failure"] == pytest.approx(1.0 - ret)
    assert d["reranking_failure"] == pytest.approx(ret - d[f"top@{cutoff}"])


def test_cutoff_above_n_candidates_raises():
    with pytest.raises(ValueError):
        decompose([["a"]], [["a", "b"]], cutoff=5, n_candidates=3)
    with pytest.raises(ValueError):
        rerank_at_k([["a"]], [["a", "b"]], cutoff=5, n_candidates=3)


def test_empty_input_is_nan():
    assert math.isnan(avg_at_k([], [], 5))
    assert all(math.isnan(v) for v in decompose([], [], cutoff=1, n_candidates=15).values())
