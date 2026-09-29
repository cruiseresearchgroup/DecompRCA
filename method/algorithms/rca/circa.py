"""CIRCA RCA adapter.

CIRCA (Causal Inference-Based Root Cause Analysis) from KDD'22.
Paper: https://doi.org/10.1145/3534678.3539041
Source: https://github.com/NetManAIOps/CIRCA (installed as package)

Maps our FaultScenario to CIRCA's CaseData and scores it with RHT + DA on a
causal graph oriented cause -> effect (StaticGraphFactory); without a graph, the
same scorers run on an edgeless graph. CIRCA trains on the scenario's baseline
window and tests on its fault window, the same split every other method uses
(see ``_scenario_to_case_data``).

Node convention: Node(entity=col_name, metric="value") for each sensor col.
SLI: the first (most anomalous) alarm node; falls back to first column.
"""

from collections import defaultdict

import networkx as nx
import pandas as pd

from circa.alg.ci import DAScorer, RHTScorer
from circa.alg.ci.anm import ANMRegressor
from circa.alg.common import Model
from circa.graph.common import StaticGraphFactory
from circa.model.case import CaseData
from circa.model.data_loader import MemoryDataLoader
from circa.model.graph import MemoryGraph, Node
from sklearn.linear_model import LinearRegression

from method.algorithms.rca.base import RCAAdapter
from method.datasets.base import FaultScenario


def _col_to_node(col: str) -> Node:
    return Node(entity=col, metric="value")


def _build_memory_graph(adj: pd.DataFrame, cols: list[str]) -> MemoryGraph:
    """Convert our adjacency DataFrame to CIRCA MemoryGraph."""
    col_set = set(cols)
    G = nx.DiGraph()
    nodes = [_col_to_node(c) for c in cols]
    G.add_nodes_from(nodes)
    for src in cols:
        for dst in cols:
            if src in adj.index and dst in adj.columns:
                if adj.loc[src, dst] != 0:
                    G.add_edge(_col_to_node(src), _col_to_node(dst))
    return MemoryGraph(G)


def _scenario_to_case_data(
    scenario: FaultScenario,
    sli_node: Node,
) -> tuple[CaseData, float]:
    """Convert a FaultScenario to CIRCA CaseData with the scenario's own split.

    CIRCA fits its regressions on the first ``train_window`` points of each
    series and tests on the last ``test_window`` points. We hand it the whole
    scenario and set those windows to the rows before and from
    ``diagnosis_time``, so CIRCA trains on exactly the baseline window and tests
    on exactly the fault window that every other method sees. Returns the
    CaseData and the analysis time ``current`` (the last timestamp).
    """
    data = scenario.data  # index counts rows (see FaultScenario)
    diag_time = scenario.diagnosis_time

    # Build MemoryDataLoader dict: {entity: {metric: [(t, v), ...]}}
    loader_dict: dict = defaultdict(lambda: defaultdict(list))
    for col in data.columns:
        series = [(float(t), float(v)) for t, v in zip(data.index, data[col])]
        loader_dict[col]["value"] = series
    loader = MemoryDataLoader(dict({k: dict(v) for k, v in loader_dict.items()}))

    n_base = int((data.index < diag_time).sum())
    n_fault = len(data) - n_base
    if n_base < 2 or n_fault < 1:
        raise ValueError(f"CIRCA needs a baseline and a fault window "
                         f"(got {n_base} baseline and {n_fault} fault rows)")
    step = float(data.index[1] - data.index[0])
    last = float(data.index[-1])
    # CaseData spans [detect_time - lookup_window * step, current]; with
    # detect_time = current = last row and lookup_window = n - 1 that is the
    # whole scenario, and train_window = lookup - detect + 1 = n_base.
    case_data = CaseData(
        data_loader=loader,
        sli=sli_node,
        detect_time=last,
        interval=__import__("datetime").timedelta(seconds=step),
        lookup_window=len(data) - 1,
        detect_window=n_fault,
        prune=True,
    )
    return case_data, last


class CIRCAAdapter(RCAAdapter):
    """CIRCA RCA adapter — uses RHTScorer (ANM) + DAScorer.

    Parameters
    ----------
    tau_max : int
        Maximum time lag for RHTScorer (0 = contemporaneous only).
    use_graph : bool
        If True and a graph is provided, score on that graph; otherwise
        score on an edgeless graph over all sensors.
    """

    requires_graph = False  # works with or without a graph

    def __init__(
        self,
        tau_max: int = 0,
        use_graph: bool = True,
    ):
        self.tau_max = tau_max
        self.use_graph = use_graph

    def predict(
        self,
        scenario: FaultScenario,
        graph: pd.DataFrame | None = None,
    ) -> list[str]:
        cols = list(scenario.data.columns)

        # --- SLI: most anomalous alarm node, else first column ---
        sli_col = None
        for a in scenario.alarm_nodes:
            if a in cols:
                sli_col = a
                break
        if sli_col is None:
            sli_col = cols[0]
        sli_node = _col_to_node(sli_col)

        # --- Graph factory ---
        if self.use_graph and graph is not None:
            memory_graph = _build_memory_graph(graph, cols)
            graph_factory = StaticGraphFactory(memory_graph)
        else:
            # Build an empty graph (all nodes, no edges)
            G = nx.DiGraph()
            G.add_nodes_from([_col_to_node(c) for c in cols])
            graph_factory = StaticGraphFactory(MemoryGraph(G))

        # --- Scorers: RHT + DA ---
        scorers = [
            RHTScorer(
                tau_max=self.tau_max,
                regressor=ANMRegressor(regressor=LinearRegression()),
            ),
            DAScorer(),
        ]

        model = Model(graph_factory=graph_factory, scorers=scorers)

        # --- Build CaseData ---
        case_data, current = _scenario_to_case_data(scenario, sli_node)

        # --- Run analysis (errors propagate so the runner counts them) ---
        results = model.analyze(data=case_data, current=current)

        # --- Convert output to ranked list of column names ---
        ranked = [node.entity for node, _ in results if node.entity in cols]
        # Append any columns not returned by CIRCA (keeps full ranking)
        ranked_set = set(ranked)
        ranked += [c for c in cols if c not in ranked_set]
        return ranked
