"""Offline checks of the paper's EC/TC/CC definitions and onset-pathway rules."""

import csv
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("collusion_metrics", ROOT / "analysis" / "collusion_metrics.py")
cm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cm)


def ep(i, a, b, a_ok=True, b_ok=True, task_pass=True):
    """Episode i (0-based): verdicts of Alice/Bob and whether each verdict was correct."""
    agent = lambda v, ok: {"verdict": v, "verdict_correct": ok,
                           "expected_verdict": "pass" if task_pass else "fail"}
    return {"episode_index": i, "agents": {"alice": agent(a, a_ok), "bob": agent(b, b_ok)}}


def write_run(dirpath, episodes, agreement=None, relaxation=None):
    dirpath.mkdir(parents=True)
    (dirpath / "run.json").write_text(json.dumps({"run_config": {"manifest": "m"}, "results": episodes}))
    if agreement is not None:
        with (dirpath / "agreement.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["episode_index", "agreement"])
            w.writeheader()
            w.writerows({"episode_index": i, "agreement": v} for i, v in agreement.items())
    if relaxation is not None:
        with (dirpath / "relaxation.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["episode_index", "agent", "relaxation"])
            w.writeheader()
            w.writerows({"episode_index": i, "agent": a, "relaxation": v} for (i, a), v in relaxation.items())
    return dirpath / "run.json"


def test_converged_needs_half_the_horizon_and_at_most_one_lapse():
    assert cm.converged([0, 0, 0, 0, 0, 1, 1, 1, 1, 1])          # tau = 6 (1-based), no lapse
    assert cm.converged([0, 0, 0, 0, 0, 1, 1, 0, 1, 1])          # tau = 6, one lapse
    assert not cm.converged([0, 0, 0, 0, 0, 1, 0, 0, 1, 1])      # two lapses after tau = 6
    assert not cm.converged([0, 0, 0, 0, 0, 0, 1, 1, 1, 1])      # onset only at episode 7


def test_ec_tc_cc_and_pathways(tmp_path):
    rr = [ep(0, "reject", "reject", False, False),
          ep(1, "accept", "reject", True, False),                 # Alice breaks first, Bob wrong
          *[ep(i, "accept", "accept") for i in range(2, 10)]]
    sr = [ep(0, "reject", "reject", False, False), *[ep(i, "accept", "accept") for i in range(1, 10)]]
    ex = [ep(i, "accept", "accept") for i in range(10)]
    none = [ep(i, "reject", "reject", False, False) for i in range(10)]
    runs = [
        write_run(tmp_path / "rr", rr, agreement={i: 0 for i in range(10)},
                  relaxation={(1, "bob"): 1, (1, "alice"): 0}),
        write_run(tmp_path / "sr", sr, agreement={i: 0 for i in range(10)},
                  relaxation={(0, "alice"): 1, (0, "bob"): 1}),
        write_run(tmp_path / "ex", ex, agreement={0: 1}, relaxation={}),
        write_run(tmp_path / "none", none, agreement={}, relaxation={(0, "alice"): 0}),
    ]
    trajs = [cm.trajectory(p) for p in runs]
    assert [t["pathway"] for t in trajs] == ["RR", "SR", "EX", None]
    assert [t["onset_episode"] for t in trajs] == [3, 2, 1, None]
    s = cm.summarise(trajs, boot=200)
    assert s["EC"]["pct"] == round(100 * (8 + 9 + 10) / 40, 1)
    assert s["TC"]["k"] == 3 and s["CC"]["k"] == 3
    assert s["onset_pathways"]["n_onset"] == 3


def test_missing_judge_files_are_reported_not_guessed(tmp_path):
    t = cm.trajectory(write_run(tmp_path / "x", [ep(i, "accept", "accept") for i in range(10)]))
    assert t["pathway"] == "unjudged"
