"""Print a live, per-episode view of what the agent did and said in money-channel runs.

    python analysis/money_monitor.py results/money/<label> [--reasoning]

For each finished episode: wallet, payment and whether it was returned, Alice's own
transfers, work calls, the verdict on correct or wrong work, balance, and short
excerpts of the verdict reasoning, the private reflection and (with --reasoning) the
model's raw reasoning before the verdict. Also flags truncated calls and API errors.
"""

import argparse
import json
from pathlib import Path


def _short(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _verdict_reasoning_text(episode: dict) -> str:
    for trace in reversed(episode.get("reasoning_traces", [])):
        if trace.get("phase") == "audit":
            content = trace.get("reasoning_trace") or {}
            for key, value in content.items():
                if "reasoning_content" in key or key.endswith("reasoning"):
                    return str(value)
    return ""


def summarize(path: Path, show_reasoning: bool) -> list[str]:
    record = json.loads(path.read_text(encoding="utf-8"))
    config = record["config"]
    lines = [
        f"== {path.stem}: {config['wallet']} wallet, {config['payment_mode']} payments, "
        f"{len(record['episodes'])}/10 episodes{' (complete)' if record.get('complete') else ''}"
    ]
    quiz = record.get("quiz") or {}
    if quiz:
        lines.append(f"   quiz: {'passed' if quiz.get('passed') else 'wrong ' + ','.join(quiz.get('wrong', []))}")
    for e in record["episodes"]:
        usage = e.get("usage", [])
        truncated = sum(1 for u in usage if u.get("finish_reason") == "length")
        errors = sum(1 for u in usage if str(u.get("response_status", "")).startswith("error"))
        cost = sum(u.get("cost_usd") or 0 for u in usage)
        work = e["work_calls"]
        flags = []
        if e["verdict"] == "accept" and not e["producer_correct"]:
            flags.append("ACCEPTED-WRONG-WORK")
        if e["payment_returned"]:
            flags.append("returned-payment")
        if e["alice_transfers"]:
            flags.append(f"alice-sent {e['alice_transfers']}")
        if e["verdict_forced"]:
            flags.append("forced-reject")
        if truncated:
            flags.append(f"{truncated} truncated")
        if errors:
            flags.append(f"{errors} api-errors")
        lines.append(
            f"   ep{e['episode']:>2} {e['task_type'][:4]} | Bob {'right' if e['producer_correct'] else 'WRONG'} "
            f"pay {e['payment']:>2} | verdict {e['verdict']:<6} ({'ok' if e['verdict_correct'] else 'bad'}) | "
            f"own {'pass' if e['alice_correct'] else 'fail'} conf {e['alice_confidence']} | "
            f"work {work.get('task', 0)}+{work.get('audit', 0)} reads {e['reflection_reads']} | "
            f"bal {e['balance_end']:>4} | ${cost:.3f} {' '.join(flags)}"
        )
        lines.append(f"        why: {_short(e['verdict_reasoning'], 220)}")
        lines.append(f"        reflection: {_short(e['reflection'], 260)}")
        if show_reasoning:
            lines.append(f"        thinking: {_short(_verdict_reasoning_text(e), 400)}")
    if record.get("debrief"):
        lines.append(f"   debrief: {_short(record['debrief']['answer'], 400)}")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    parser.add_argument("--reasoning", action="store_true")
    args = parser.parse_args()
    for path in sorted(Path(args.directory).glob("rep*.json")):
        print("\n".join(summarize(path, args.reasoning)))


if __name__ == "__main__":
    main()
