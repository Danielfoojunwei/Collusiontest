"""Run money-channel repetitions with resumable, per-episode persistence.

Each repetition writes <out>/rep<NNN>.json after every episode, plus an LLM usage
journal (every call, including retries) and a human-readable progress log. A
partially finished repetition resumes from its next episode: the compact memory,
the ledger and the scripted producer's notes are all rebuilt from the saved record.

    python -m experiments.money --model openrouter/qwen/qwen3.8-27b \
        --reasoning-effort high --start 1 --count 50 --label qwen38_high
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

from experiments.llm import get_litellm_version
from experiments.money.config import (
    AGENT,
    EPISODES,
    PRODUCER,
    SCRIPTED_START_BALANCE,
    WALLETS,
    MoneyRunConfig,
)
from experiments.money.episode import Transcript, prose_turn, run_money_episode, run_quiz
from experiments.money.ledger import Ledger
from experiments.money.prompts import (
    DEBRIEF_PROMPT,
    SUSPICION_PROMPT,
    memory_message,
    scripted_reflection,
    system_prompt,
)
from experiments.money.schedule import episode_plans, run_assignment
from experiments.tasks import DEFAULT_TASK_SEQUENCES, read_task_pairs

SCHEMA_VERSION = 1
DEFAULT_SEED = 20261007


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, path)


def run_cost(record: dict[str, Any]) -> float:
    total = 0.0
    for section in [record.get("quiz") or {}, record.get("debrief") or {}, *record.get("episodes", [])]:
        for usage in section.get("usage", []):
            cost = usage.get("cost_usd")
            if isinstance(cost, (int, float)):
                total += float(cost)
    return total


def _base_messages(config: MoneyRunConfig) -> list[dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": system_prompt(start_balance=WALLETS[config.wallet]),
        }
    ]


def _episode_messages(config: MoneyRunConfig, earlier: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compact memory: system prompt, then earlier results and own reflections only."""
    messages = _base_messages(config)
    if earlier:
        messages.append({"role": "user", "content": memory_message(earlier)})
    return messages


def run_repetition(
    *,
    config: MoneyRunConfig,
    out_dir: Path,
    repo_root: Path,
    sequences_dir: str = DEFAULT_TASK_SEQUENCES,
    log: Callable[[str], None] = print,
    spend_left: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Run (or resume) one repetition and return its record."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"rep{config.repetition:03d}.json"
    journal = out_dir / f"rep{config.repetition:03d}.usage.jsonl"
    manifest = repo_root / sequences_dir / f"rep{config.repetition:03d}_sampled_manifest.json"
    pairs = read_task_pairs(manifest, repo_root)
    if len(pairs) != EPISODES:
        raise ValueError(f"{manifest} has {len(pairs)} episodes, expected {EPISODES}")
    plans = episode_plans(config.repetition, config.seed)

    if path.exists():
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["config"] != config.__dict__:
            raise ValueError(f"{path} was made with different settings: {record['config']}")
        if record.get("complete"):
            log(f"rep{config.repetition:03d}: already complete")
            return record
        ledger = Ledger.from_records(record["ledger"])
        log(f"rep{config.repetition:03d}: resuming after episode {len(record['episodes'])}")
    else:
        ledger = Ledger.opened({AGENT: WALLETS[config.wallet], PRODUCER: SCRIPTED_START_BALANCE})
        record = {
            "schema_version": SCHEMA_VERSION,
            "config": config.__dict__,
            "manifest": str(manifest.relative_to(repo_root)),
            "plans": [plan.__dict__ for plan in plans],
            "litellm_version": get_litellm_version(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "quiz": None,
            "episodes": [],
            "ledger": ledger.records(),
            "debrief": None,
            "complete": False,
        }

    while len(record["episodes"]) < EPISODES:
        if spend_left is not None and spend_left() <= 0:
            log("spend limit reached; stopping before the next episode")
            _write_atomic(path, record)
            return record
        index = len(record["episodes"])
        messages = _episode_messages(config, record["episodes"])
        if index == 0 and record["quiz"] is None:
            transcript = Transcript()
            quiz = run_quiz(
                state=_quiz_state(), ledger=ledger, config=config, messages=messages,
                transcript=transcript, journal_path=journal, log=log,
            )
            quiz.update({"reasoning_traces": transcript.reasoning, "usage": transcript.usage})
            record["quiz"] = quiz
            log(f"rep{config.repetition:03d}: quiz {'passed' if quiz['passed'] else 'wrong: ' + ', '.join(quiz['wrong'])}")
        producer_notes = [
            scripted_reflection(
                e["episode"],
                config.payment_mode,
                e["payment"],
                accepted_by_alice=e["verdict"] == "accept",
                seed=f"{config.seed}:{config.repetition}",
            )
            for e in record["episodes"]
        ]
        total_before = sum(e["episode_score"] for e in record["episodes"])
        episode = run_money_episode(
            pair=pairs[index],
            plan=plans[index],
            episode_index=index,
            config=config,
            ledger=ledger,
            messages=messages,
            producer_reflections=producer_notes,
            total_score_before=total_before,
            repo_root=repo_root,
            journal_path=journal,
            log=log,
        )
        episode["messages"] = [m for m in messages if m.get("role") != "system"]
        record["episodes"].append(episode)
        record["ledger"] = ledger.records()
        _write_atomic(path, record)

    if record["debrief"] is None:
        transcript = Transcript()
        messages = _episode_messages(config, record["episodes"])
        answer = prose_turn(
            prompt=DEBRIEF_PROMPT, phase="debrief", config=config, messages=messages,
            transcript=transcript, episode_index=EPISODES, journal_path=journal,
        )
        messages += [
            {"role": "user", "content": DEBRIEF_PROMPT},
            {"role": "assistant", "content": answer},
        ]
        # Suspicion probe last, after the debrief and after every decision is made.
        suspicion = prose_turn(
            prompt=SUSPICION_PROMPT, phase="suspicion_probe", config=config, messages=messages,
            transcript=transcript, episode_index=EPISODES, journal_path=journal,
        )
        record["debrief"] = {
            "answer": answer,
            "suspicion_probe": suspicion,
            "reasoning_traces": transcript.reasoning,
            "usage": transcript.usage,
        }
    record["complete"] = True
    record["finished_at"] = datetime.now(timezone.utc).isoformat()
    record["final_balance"] = ledger.balance(AGENT)
    record["score"] = sum(e["episode_score"] for e in record["episodes"])
    record["cost_usd"] = round(run_cost(record), 6)
    _write_atomic(path, record)
    log(f"rep{config.repetition:03d}: complete, score {record['score']}, cost ${record['cost_usd']:.3f}")
    return record


def _quiz_state() -> dict[str, Any]:
    from experiments.protocol.state import create_channel_state

    state = create_channel_state(episode_id="quiz")
    state["phase"] = "quiz"
    return state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m experiments.money")
    parser.add_argument("--model", required=True)
    parser.add_argument("--reasoning-effort", required=True)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--max-output-tokens", type=int, default=16000)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output-dir", default="results/money")
    parser.add_argument(
        "--max-spend-usd",
        type=float,
        default=0.0,
        help="Stop before the next episode once this invocation's measured cost reaches it (0 = off).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    out_dir = repo_root / args.output_dir / args.label
    out_dir.mkdir(parents=True, exist_ok=True)
    progress = (out_dir / "progress.log").open("a", encoding="utf-8")

    def log(message: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {message}"
        print(line, flush=True)
        progress.write(line + "\n")
        progress.flush()

    # Cost already on disk for each repetition when this invocation first touched it.
    baseline: dict[int, float] = {}

    def spend_left() -> float:
        if args.max_spend_usd <= 0:
            return float("inf")
        total = 0.0
        for rep, before in baseline.items():
            path = out_dir / f"rep{rep:03d}.json"
            if path.exists():
                total += run_cost(json.loads(path.read_text(encoding="utf-8"))) - before
        return args.max_spend_usd - total

    for repetition in range(args.start, args.start + args.count):
        assignment = run_assignment(repetition, args.seed)
        config = MoneyRunConfig(
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            temperature=args.temperature,
            max_output_tokens=args.max_output_tokens,
            repetition=repetition,
            wallet=assignment.wallet,
            payment_mode=assignment.payment_mode,
            seed=args.seed,
        )
        existing = out_dir / f"rep{repetition:03d}.json"
        baseline[repetition] = (
            run_cost(json.loads(existing.read_text(encoding="utf-8"))) if existing.exists() else 0.0
        )
        log(f"rep{repetition:03d}: start ({assignment.wallet} wallet, {assignment.payment_mode} payments)")
        record = run_repetition(
            config=config, out_dir=out_dir, repo_root=repo_root, log=log, spend_left=spend_left,
        )
        if not record.get("complete"):
            log("stopped before completing all repetitions")
            sys.exit(2)
    log(f"done: repetitions {args.start}-{args.start + args.count - 1}")


if __name__ == "__main__":
    main()
