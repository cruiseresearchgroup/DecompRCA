"""Regression test: CIRCA uses the scenario's own baseline/fault split.

Every method scores the rows before ``diagnosis_time`` (baseline) against the
rows from it (fault). CIRCA must train on exactly the baseline rows and test on
exactly the fault rows, with no window parameters of its own and no padding.
"""

import numpy as np
import pandas as pd
import pytest

from method.algorithms.rca.circa import CIRCAAdapter, _col_to_node, _scenario_to_case_data
from method.datasets.base import FaultScenario


def _scenario(n_base, n_fault, seed=0):
    idx = np.arange(n_base + n_fault, dtype=float)
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({"a": rng.normal(size=len(idx)), "b": rng.normal(size=len(idx))}, index=idx)
    return FaultScenario("s", df, float(n_base), ["a"], ["b"])


@pytest.mark.parametrize("n_base,n_fault", [(1800, 600), (360, 361), (900, 900), (30, 5)])
def test_train_and_test_windows_are_the_scenario_split(n_base, n_fault):
    sc = _scenario(n_base, n_fault)
    case, current = _scenario_to_case_data(sc, _col_to_node("b"))
    assert case.train_window == n_base
    assert case.test_window == n_fault
    assert current == sc.data.index[-1]
    series = case.load_data(current=current)[_col_to_node("a")]
    assert len(series) == n_base + n_fault                      # whole scenario, no padding
    np.testing.assert_allclose(series[:n_base], sc.data["a"].values[:n_base])
    np.testing.assert_allclose(series[-n_fault:], sc.data["a"].values[n_base:])


def test_shift_in_fault_window_is_ranked_first():
    sc = _scenario(300, 100, seed=1)
    sc.data.loc[sc.data.index >= 300, "a"] += 8.0                # cause shifts at detection
    ranked = CIRCAAdapter(use_graph=False).predict(sc)
    assert ranked[0] == "a"


def test_needs_both_windows():
    sc = _scenario(1, 10)
    with pytest.raises(ValueError):
        _scenario_to_case_data(sc, _col_to_node("b"))
