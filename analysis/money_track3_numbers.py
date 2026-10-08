"""Every headline number for the Track 3 write-up, recomputed from the run files and judge labels.

    python analysis/money_track3_numbers.py [--out docs/money_track3_numbers.json]

Sections: inventory; fair game (wallet 20) unchecked accepts split by ability to pay, mutual
accepts, harm; randomised offers; stratified coordination; judge labels by model, condition and
source (agreed labels only where both judges ran).
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.money_collusion import AGENTS, load, unsupported  # noqa: E402
from analysis.money_coordination import analyse as coordination  # noqa: E402
from analysis.money_offers import analyse as offers  # noqa: E402
from experiments.money.config import TOOL_COST  # noqa: E402

ROOT = Path("results/money")


def model_of(run):
    return run["config"]["alice"]["model"].split("/")[-1]


def fair_game(runs):
    xs = [(e, e["agents"][a]) for r in runs for e in r["episodes"] for a in AGENTS]
    able = [x for _, x in xs if x["balance_at_check"] >= TOOL_COST]
    broke = [x for _, x in xs if x["balance_at_check"] < TOOL_COST]
    inj = [x for _, x in xs if x.get("partner_injected")]
    return {
        "runs": len(runs), "verdicts": len(xs),
        "unchecked_accept_able": sum(map(unsupported, able)), "able": len(able),
        "unchecked_accept_broke": sum(map(unsupported, broke)), "broke": len(broke),
        "mutual_unchecked_both_able": sum(
            all(unsupported(e["agents"][a]) and e["agents"][a]["balance_at_check"] >= TOOL_COST for a in AGENTS)
            for r in runs for e in r["episodes"]),
        "mutual_unchecked_any": sum(all(unsupported(e["agents"][a]) for a in AGENTS) for r in runs for e in r["episodes"]),
        "injected_shown": len(inj), "injected_accepted": sum(x["verdict"] == "accept" for x in inj),
        "injected_accepted_unchecked": sum(map(unsupported, inj)),
        "injected_checked": sum(x["checked"] for x in inj),
        "injected_checked_caught": sum(x["checked"] and x["verdict"] != "accept" for x in inj),
    }


def judges(run_meta):
    path = Path("docs/money_judges/judgements.jsonl")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    by = defaultdict(dict)
    for r in rows:
        by[r["id"]][r["judge"]] = r["label"]
    out = {}
    for signal in ("M", "T", "W", "R"):
        table = defaultdict(Counter)
        for item_id, labels in by.items():
            parts = item_id.split("-")
            if f"-{signal}" not in item_id or "A" not in labels:
                continue
            if signal in ("M", "T", "W") and "B" in labels and labels["A"] != labels["B"]:
                label = "DISAGREE"
            else:
                label = labels["A"]
            run = item_id.split("-e")[0].split("-debrief")[0]
            model, cond = run_meta.get(run, ("?", "?"))
            key = f"{model} | {cond}"
            if signal == "W":
                source = "debrief" if "-debrief-" in item_id else "in_episode"
                key += f" | {source}"
            table[key][label] += 1
        out[signal] = {k: dict(v) for k, v in sorted(table.items())}
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    groups = {d.name: load([d]) for d in sorted(ROOT.iterdir()) if d.is_dir()}
    groups = {k: v for k, v in groups.items() if v}
    run_meta = {r["_name"]: (model_of(r), r["config"]["condition"]) for v in groups.values() for r in v}
    report = {
        "inventory": {k: {"runs": len(v), "model": model_of(v[0]), "condition": v[0]["config"]["condition"],
                          "wallet": v[0]["rules"]["wallet"] if v[0].get("rules") else None} for k, v in groups.items()},
        "fair_game_wallet20": {k: fair_game(v) for k, v in groups.items() if k.startswith(("v86_", "v87_"))},
        "offers": {k: offers(v, 5000) for k, v in groups.items() if "offer" in k},
        "coordination_stratified": {k: coordination(v, 2000) for k, v in groups.items()
                                    if "no_rule" in k and k.startswith("v8")},
        "judges": judges(run_meta),
    }
    text = json.dumps(report, indent=1)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text[:200])


if __name__ == "__main__":
    main()
