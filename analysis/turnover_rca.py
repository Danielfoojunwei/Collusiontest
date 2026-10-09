"""Root-cause analysis: what moves an agent from REJECT to ACCEPT in the next episode?

Reads ``judgements.csv`` (from ``turnover_insights.py``) and every ``run.json`` under
``--in``. Each row of the transition table is one agent's verdict in episode n
followed by the same agent's verdict in episode n+1, where the agent remembers n.
A fresh Bob remembers nothing before the fork, so its chain starts there; prefix
transitions are counted once, not once per arm.

Writes ``rca.json`` and prints the tables.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from math import comb
from pathlib import Path
from typing import Any

IMPOSSIBLE_RE = re.compile(
    r"impossible|infeasible|constraint|limit|too (long|large)|technicalit|rigid", re.I)


def fisher(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for [[a, b], [c, d]]."""
    n, r1, c1 = a + b + c + d, a + b, a + c
    if n == 0:
        return 1.0
    p = lambda x: comb(r1, x) * comb(n - r1, c1 - x) / comb(n, c1)
    p0 = p(a)
    lo, hi = max(0, c1 - (n - r1)), min(r1, c1)
    return min(1.0, sum(p(x) for x in range(lo, hi + 1) if p(x) <= p0 * (1 + 1e-9)))


def rate(k: int, n: int) -> str:
    return f"{k}/{n} ({100 * k / n:.0f}%)" if n else "0/0"


def load_rows(root: Path) -> dict[tuple, dict[str, Any]]:
    rows = {}
    for r in csv.DictReader(open(root / "judgements.csv")):
        rows[(r["seq"], r["arm"], int(r["episode"]), r["judge"])] = r
    return rows


def reflections(root: Path) -> dict[tuple, str]:
    out = {}
    for seq_dir in sorted(root.glob("rep*")):
        for arm in ("prefix", "control", "replacement"):
            p = seq_dir / arm / "run.json"
            if not p.exists():
                continue
            for n, e in enumerate(json.loads(p.read_text())["results"], 1):
                for j in ("alice", "bob"):
                    out[(seq_dir.name, arm, n, j)] = e["agents"][j].get("reflection") or ""
    return out


def chains(rows: dict[tuple, dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Ordered verdict histories, one per (agent, memory line)."""
    by = defaultdict(dict)
    for (seq, arm, n, j), r in rows.items():
        by[(seq, arm, j)][n] = r
    out = []
    for (seq, arm, j), eps in by.items():
        if arm == "prefix":
            out.append([eps[n] for n in sorted(eps)])
            continue
        start = min(eps)
        chain = [eps[n] for n in sorted(eps)]
        if not (arm == "replacement" and j == "bob"):
            # Remembering agent: link the last prefix episode to the first arm episode.
            last = by.get((seq, "prefix", j), {}).get(start - 1)
            if last is not None:
                chain = [last] + chain
        out.append(chain)
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="inp", default="results/turnover")
    root = Path(p.parse_args().inp)
    rows = {k: v for k, v in load_rows(root).items() if v["forced"] != "True"}
    refl = reflections(root)
    acc = lambda r: r["verdict"] == "accept"

    # Transitions: (state at n) -> accept at n+1, with candidate causes measured at n / n+1.
    T = []
    for chain in chains(rows):
        for prev, nxt in zip(chain, chain[1:]):
            if int(nxt["episode"]) != int(prev["episode"]) + 1:
                continue
            peer = "bob" if prev["judge"] == "alice" else "alice"
            peer_prev = rows.get((prev["seq"], prev["arm"], int(prev["episode"]), peer))
            peer_nxt = rows.get((nxt["seq"], nxt["arm"], int(nxt["episode"]), peer))
            T.append({
                "seq": prev["seq"], "arm": nxt["arm"], "judge": prev["judge"],
                "fresh_bob": nxt["arm"] == "replacement" and prev["judge"] == "bob",
                "prev_accept": acc(prev),
                "told_wrong": prev["verdict_correct"] != "True",
                "reflection_blames_rule": bool(IMPOSSIBLE_RE.search(
                    refl.get((prev["seq"], prev["arm"], int(prev["episode"]), prev["judge"]), ""))),
                "peer_accepted_me_prev": bool(peer_prev and acc(peer_prev)),
                "peer_proposes_now": bool(peer_nxt and peer_nxt["judge_proposal"] == "True"),
                "leak_now": float(nxt["leak_frac"]),
                "task_type_now": nxt["task_type"],
                "reward_prev": int(prev["reward"] or 0),
                "next_accept": acc(nxt),
            })

    out: dict[str, Any] = {"n_transitions": len(T)}

    def split(name: str, subset: list[dict[str, Any]], key: str) -> None:
        yes = [t for t in subset if t[key]]
        no = [t for t in subset if not t[key]]
        a, b = sum(t["next_accept"] for t in yes), len(yes)
        c, d = sum(t["next_accept"] for t in no), len(no)
        out[name] = {"if_true": rate(a, b), "if_false": rate(c, d),
                     "fisher_p": round(fisher(a, b - a, c, d - c), 4)}

    rej = [t for t in T if not t["prev_accept"]]
    # H1: the verdict review ("you were wrong") after a REJECT is what flips agents.
    split("H1 after REJECT: told wrong -> accept next", rej, "told_wrong")
    split("H1 fresh Bob only", [t for t in rej if t["fresh_bob"]], "told_wrong")
    # H1b: does the reflection carry it (blames the rule)?
    split("H1b after REJECT told wrong: reflection blames rule -> accept next",
          [t for t in rej if t["told_wrong"]], "reflection_blames_rule")
    # H2: reciprocity - peer accepted my work last episode.
    split("H2 after REJECT: peer accepted me last episode -> accept next", rej, "peer_accepted_me_prev")
    # H3: peer proposes relaxing the rule in this episode.
    split("H3 after REJECT: peer proposes relaxed rule now -> accept", rej, "peer_proposes_now")
    # H4: more of the peer's log arrives (evidence) in this episode.
    for t in rej:
        t["leak_high"] = t["leak_now"] >= 0.05
    split("H4 after REJECT: >=5% of peer log delivered now -> accept", rej, "leak_high")
    # H5: reward after the previous episode was positive (confounded with H1 via the peer).
    for t in rej:
        t["reward_pos"] = t["reward_prev"] > 0
    split("H5 after REJECT: positive shared reward last episode -> accept next", rej, "reward_pos")

    # Stratify H1 by H2 to separate the feedback signal from reciprocity.
    for flag in (True, False):
        sub = [t for t in rej if t["peer_accepted_me_prev"] == flag]
        split(f"H1 within peer_accepted_me_prev={flag}", sub, "told_wrong")

    # Persistence: after an ACCEPT that the review called right, do agents keep accepting?
    accs = [t for t in T if t["prev_accept"]]
    split("After ACCEPT: told wrong -> accept again", accs, "told_wrong")

    # Fresh Bob trajectories, for the slide.
    traj = defaultdict(list)
    for t in sorted((t for t in T if t["fresh_bob"]), key=lambda t: t["seq"]):
        traj[t["seq"]].append(("W" if t["told_wrong"] else "R") + ("→A" if t["next_accept"] else "→R"))
    out["fresh_bob_transitions"] = dict(traj)

    (root / "rca.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
