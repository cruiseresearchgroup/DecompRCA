"""Regression test: causal-graph direction through every graph-based baseline.

Ground truth: A -> C <- B, C -> D. The root causes are A and B; D is the most
downstream node. A correct graph-based RCA method must rank A and B above D.

Run:  python -m pytest tests/test_graph_direction.py   (or python tests/test_graph_direction.py)
"""

import numpy as np
import pandas as pd
from causallearn.search.ConstraintBased.FCI import fci
from causallearn.search.ConstraintBased.PC import pc

from method.algorithms.cd.fci import _causallearn_fci_to_directed_binary
from method.algorithms.cd.pc import _causallearn_to_directed_binary
from method.algorithms.rca.circa import _build_memory_graph, _col_to_node
from method.algorithms.rca.pagerank import PageRankAdapter
from method.algorithms.rca.random_walk import RandomWalkAdapter
from method.datasets.base import FaultScenario

NAMES = ["A", "B", "C", "D"]
TRUE_EDGES = {("A", "C"), ("B", "C"), ("C", "D")}


def _data(n=5000, seed=0):
    rng = np.random.default_rng(seed)
    a, b = rng.normal(size=n), rng.normal(size=n)
    c = a + b + 0.5 * rng.normal(size=n)
    d = c + 0.5 * rng.normal(size=n)
    return np.c_[a, b, c, d]


def _edges(binary: pd.DataFrame) -> set[tuple[str, str]]:
    return {(i, j) for i in binary.index for j in binary.columns if binary.loc[i, j] != 0}


def _scenario() -> FaultScenario:
    df = pd.DataFrame(_data(200), columns=NAMES)
    return FaultScenario(scenario_id="synthetic", data=df, diagnosis_time=0.0,
                         ground_truth_causes=["A"], alarm_nodes=["D"])


def test_causallearn_encoding():
    """causal-learn marks i -> j as graph[i,j] = -1 (tail), graph[j,i] = 1 (arrow)."""
    g = pc(_data(), 0.01, "fisherz", show_progress=False).G.graph
    found = {(NAMES[i], NAMES[j]) for i in range(4) for j in range(4)
             if g[i, j] == -1 and g[j, i] == 1}
    assert found == TRUE_EDGES


def test_pc_converter_is_cause_to_effect():
    g = pc(_data(), 0.01, "fisherz", show_progress=False).G.graph
    assert _edges(_causallearn_to_directed_binary(g, NAMES)) == TRUE_EDGES


def test_fci_converter_is_cause_to_effect():
    """FCI returns A o-> C <-o B and C -> D; every edge must come out cause -> effect."""
    g, _ = fci(_data(), independence_test_method="fisherz", alpha=0.01,
               show_progress=False, verbose=False)
    assert _edges(_causallearn_fci_to_directed_binary(g.graph, NAMES)) == TRUE_EDGES


def _true_graph() -> pd.DataFrame:
    m = pd.DataFrame(0.0, index=NAMES, columns=NAMES)
    for i, j in TRUE_EDGES:
        m.loc[i, j] = 1.0
    return m


def test_pagerank_ranks_causes_first():
    ranked = PageRankAdapter().predict(_scenario(), graph=_true_graph())
    assert set(ranked[:2]) == {"A", "B"} and ranked[-1] == "D"


def test_random_walk_ranks_causes_first():
    ranked = RandomWalkAdapter(num_loop=4000).predict(_scenario(), graph=_true_graph())
    assert set(ranked[:2]) == {"A", "B"} and ranked[-1] == "D"


def test_circa_parents_are_causes():
    g = _build_memory_graph(_true_graph(), NAMES)
    parents = {n.entity for n in g.parents(_col_to_node("C"))}
    assert parents == {"A", "B"}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
