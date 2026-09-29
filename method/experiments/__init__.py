"""Controlled experiments behind the paper's appendix tables.

Each module is runnable as ``python -m method.experiments.<module>`` and
writes CSV/JSON outputs under ``method/results/<experiment>/``:

  controlled_pools    retrieval-controlled candidate pools (reserved spot for
                      the true cause) + rule rankers, BARO and RCD on them
  controlled_baselines  epsilon-Diagnosis and graph baselines on the pools
  controlled_llm      LLM reranker on the pools (API calls only with --run-llm;
                      offline re-scoring from a response cache with --cache-dir)
  same_candidate      rule rankers + Borda on the LLM's exact candidate lists
  hvac_baselines      end-to-end HVAC baselines (seeded)
  hvac_pools          HVAC Retrieval@K, pools and pool baselines
  tdet_sensitivity    detection-timestamp perturbation of Retrieval@K
  longwindow_graphs   graph heads on global graphs from long normal windows
  anonymize           de-identification maps for the anonymization control
  tables              assemble paper-table CSVs from the outputs above
  run_all             run everything in order
"""
