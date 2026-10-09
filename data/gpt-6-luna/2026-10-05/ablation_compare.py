# Usage (from repo root): PYTHONPATH=. python data/gpt-6-luna/2026-10-05/ablation_compare.py results/turnover-gpt6luna
# Per-arm post-fork verdicts, joint-ACCEPT kinds, verdict accuracy and suffix cost.
import json, sys
from pathlib import Path
from experiments.turnover import joint_accept_kind, run_spend
out = Path(sys.argv[1]); res = {}
for seq in sorted(out.glob("rep*/checkpoint")):
    sd = seq.parent
    for arm in ("control", "replacement", "replacement-no-verdict-review"):
        r = json.loads((sd / arm / "run.json").read_text())
        fork = r["turnover"]["fork_after_episode"]; cl = r["run_config"]["char_limit"]
        eps = r["results"][fork:fork + 3]
        v = {a: [e["agents"][a]["verdict"] for e in eps] for a in ("alice", "bob")}
        corr = [int(bool(e["agents"][a].get("verdict_correct"))) for e in eps for a in ("alice", "bob")]
        res[f"{sd.name}/{arm}"] = {
            "verdicts": v, "bob_first_accept": v["bob"][0] == "accept",
            "bob_accept_ep2_3": sum(x == "accept" for x in v["bob"][1:3]),
            "joint": [joint_accept_kind(e, cl) for e in eps],
            "verdict_acc": f"{sum(corr)}/{len(corr)}",
            "suffix_cost_usd": round(run_spend(eps)[0], 4)}
print(json.dumps(res, indent=1))
