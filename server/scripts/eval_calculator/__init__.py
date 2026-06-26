"""Offline evaluation of the EKT calculator's variable extraction against saved ground truth.

`grade` is the pure scoring core; `capture` re-runs one position's extraction headlessly to its Gate B
proposals; `run` is the CLI that joins saved ground truth to a fresh re-run and writes scored results.
"""
