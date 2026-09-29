"""PC algorithm adapter — calls causallearn directly with correct directed conversion."""

import numpy as np
import pandas as pd
from causallearn.search.ConstraintBased.PC import pc as causallearn_pc

from method.algorithms.cd.base import CDAdapter


def _causallearn_to_directed_binary(graph_matrix: np.ndarray, node_names: list) -> pd.DataFrame:
    """Convert a causallearn -1/0/1 graph to a cause→effect binary adjacency.

    causallearn stores, in graph[x, y], the edge mark at x's end of the x–y
    edge (-1 = tail, 1 = arrowhead). So:
        graph[i,j]=-1, graph[j,i]=1   →  i → j    (binary[i,j]=1)
        graph[i,j]=graph[j,i]=-1      →  i — j    (both)
        graph[i,j]=graph[j,i]=1       →  i <-> j  (both)

    The output follows the row → column convention: binary[i,j]=1 means
    i → j (cause → effect). Graph heads that walk toward causes reverse it
    themselves. Note that RCAEval's page_rank_preprocess() emits the opposite
    (effect → cause) orientation, which its PageRank consumes untransposed.
    """
    n = len(node_names)
    binary = np.zeros((n, n), dtype=float)
    for a in range(n):
        for b in range(n):
            va, vb = graph_matrix[a, b], graph_matrix[b, a]
            if va == 0 and vb == 0:
                pass
            elif va == -1 and vb == -1:          # undirected a -- b
                binary[a, b] = binary[b, a] = 1
            elif va == -1 and vb == 1:           # tail at a, arrow at b: a -> b
                binary[a, b] = 1
            elif va == 1 and vb == -1:           # arrow at a, tail at b: a <- b
                binary[b, a] = 1
            elif va == 1 and vb == 1:            # bidirected a <-> b
                binary[a, b] = binary[b, a] = 1
    return pd.DataFrame(binary, index=node_names, columns=node_names)


class PCAdapter(CDAdapter):
    """PC algorithm — calls causallearn directly, preserving edge directionality."""

    def __init__(self, alpha: float = 0.05, indep_test: str = "fisherz", stable: bool = True):
        # Defaults match RCAEval's pc_default (causallearn defaults).
        self.alpha = alpha
        self.indep_test = indep_test
        self.stable = stable

    def fit(self, normal_data: pd.DataFrame) -> pd.DataFrame:
        print(f"  PC: learning on {normal_data.shape[0]} rows × {normal_data.shape[1]} cols …")
        node_names = normal_data.columns.tolist()

        # Match RCAEval's pc_default: ffill then to_numpy, no np.abs() applied.
        data_clean = normal_data.ffill().fillna(0.0)
        np_data = data_clean.to_numpy().astype(float)

        result = causallearn_pc(
            np_data,
            alpha=self.alpha,
            indep_test=self.indep_test,
            stable=self.stable,
            show_progress=False,
            node_names=node_names,
        )
        graph_matrix = result.G.graph  # shape (n, n), values in {-1, 0, 1}

        adj = _causallearn_to_directed_binary(graph_matrix, node_names)
        n_edges = int((adj.values != 0).sum())
        print(f"  PC: found {n_edges} directed edges")
        return adj
