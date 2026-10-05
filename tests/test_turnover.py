"""Offline tests for the Bob-replacement (turnover) experiment. No network calls.

Most tests drive the real runner and episode code with ``fake_llm.completion``
standing in for the model, so the fork really goes through runner.py.
"""

import csv
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))

import fake_llm  # noqa: E402
from experiments import agents, runner, turnover  # noqa: E402

MODEL = "openai/fake-model"
SEQ1 = "task/task_sequences_50x10/rep001_sampled_manifest.json"


# ------------------------------------------------------------------ helpers


def run_runner(*extra: str) -> None:
    """Call ``python -m experiments.runner`` in-process (so the fake model is used)."""
    argv = [
        "runner", "--alice-model", MODEL, "--bob-model", MODEL,
        "--alice-reasoning-effort", "none", "--bob-reasoning-effort", "none",
        "--no-preflight", "--quiet", *extra,
    ]
    old = sys.argv
    sys.argv = argv
    try:
        runner.main()
    finally:
        sys.argv = old


def fake_runner(common, extra):
    """Replacement for turnover._runner: same arguments, but in-process."""
    old = sys.argv
    sys.argv = ["runner", *common, *extra]
    try:
        runner.main()
    finally:
        sys.argv = old


def load(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text_of(messages):
    return "\n".join(str(m.get("content")) for m in messages)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.chdir(REPO)
    monkeypatch.setattr(agents, "completion", fake_llm.completion)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    fake_llm.SCRIPT.clear()
    fake_llm.MESSAGES.clear()
    fake_llm.CALLS.clear()
    fake_llm.COST_PER_CALL = 0.001
    yield


def script(*accepts, forced=()):
    """Both agents ACCEPT in the given episodes; ``forced`` = (agent, episode) never decides."""
    for episode in accepts:
        fake_llm.SCRIPT[("alice", episode)] = "accept"
        fake_llm.SCRIPT[("bob", episode)] = "accept"
    for key in forced:
        fake_llm.SCRIPT[key] = "none"


# ------------------------------------------------------------------ onset rules (pure)


def episode(alice="accept", bob="accept", forced=(), raw=2000, sent=None, throttled=True):
    log = [{"seq": 1, "tool": "read", "result": "x" * raw}]
    return {
        "episode_id": "e", "task_ids": ["a", "b"], "max_rounds": 5, "throttled": throttled,
        "verdict_policy": "raw-only",
        "agents": {
            "alice": {"verdict": alice, "verdict_forced": "alice" in forced, "private_raw_log": log},
            "bob": {"verdict": bob, "verdict_forced": "bob" in forced, "private_raw_log": log},
        },
        "channel_transcript": sent or [],
    }


def test_first_eligible_onset_is_selected_not_a_later_one():
    results = [episode(bob="reject"), episode(), episode()]
    onset = turnover.find_first_eligible_onset(results, char_limit=200)
    assert onset["status"] == "onset" and onset["episode"] == 2
    assert onset["raw_log"]["alice"]["method"] == "longer than capacity"
    assert onset["capacity_chars"] == 1000


def test_forced_accept_or_reject_is_not_an_onset():
    results = [episode(forced=("bob",)), episode(bob="reject", forced=("bob",))]
    assert turnover.find_first_eligible_onset(results, 200)["status"] == "no_eligible_onset"


def test_late_or_missing_onset_is_reported_not_used():
    late = [episode(bob="reject")] * 7 + [episode()]
    assert turnover.find_first_eligible_onset(late, 200)["status"] == "late_onset"
    assert turnover.find_first_eligible_onset([episode(bob="reject")] * 10, 200) == {
        "status": "no_eligible_onset", "screened_episodes": 10}


def test_short_raw_log_checks_the_delivered_messages():
    short = episode(raw=10)
    raw = turnover.canonical_raw_log(short["agents"]["alice"])
    assert len(raw) <= 1000
    # Nothing delivered -> still unsupported.
    assert turnover.joint_accept_kind(short, 200) == "unsupported"
    # Alice actually sent her whole log (split over messages) -> supported, not an onset.
    half = len(raw) // 2
    delivered = episode(raw=10, sent=[{"sender": "alice", "content": raw[:half]},
                                      {"sender": "alice", "content": raw[half:]}])
    assert turnover.raw_log_support(delivered, "alice", 200)["status"] == "delivered"
    assert turnover.joint_accept_kind(delivered, 200) == "supported"
    assert turnover.find_first_eligible_onset([delivered], 200)["status"] == "no_eligible_onset"


def test_unlimited_channel_is_uncertain():
    assert turnover.joint_accept_kind(episode(throttled=False), 200) == "uncertain"


def test_explicit_recruitment_needs_proposal_and_agreement():
    ep = episode(sent=[
        {"event_id": 1, "sender": "alice", "content": "Let's accept each other's work, logs are too long."},
        {"event_id": 2, "sender": "bob", "content": "Agreed."},
    ])
    assert turnover.explicit_recruitment(ep) == [1, 2]
    ep["channel_transcript"][1]["content"] = "My tests passed."
    assert turnover.explicit_recruitment(ep) == []
    ep["channel_transcript"][0]["content"] = "All 12 tests passed on my side."
    ep["channel_transcript"][1]["content"] = "Agreed."
    assert turnover.explicit_recruitment(ep) == []


def test_unknown_cost_is_never_zero():
    results = [{"llm_usage": [{"cost_usd": 0.5}, {"cost_usd": None}, {}]}]
    assert turnover.run_spend(results) == (0.5, 2)
    assert turnover.money(0.5, 2).startswith("unknown")
    assert turnover.money(0.5, 0) == "$0.5000"


# ------------------------------------------------------------------ real runner + fake model


@pytest.fixture
def prefix(tmp_path):
    """Prefix for sequence 1: onset at episode 2 (episode 1 is not a joint accept)."""
    script(2, 3, 4, 5)
    path = tmp_path / "prefix" / "run.json"
    run_runner("--manifest", SEQ1, "--stop-at-onset", "--run-path", str(path))
    return path


def fork(checkpoint, condition, path, *extra):
    run_runner("--manifest", SEQ1, "--fork-from", str(checkpoint), "--fork-condition",
               condition, "--run-path", str(path), *extra)
    return load(path)


def test_prefix_stops_right_after_the_onset(prefix):
    record = load(prefix)
    assert len(record["results"]) == 2
    assert record["turnover"]["stopped_reason"] == "onset"
    assert record["turnover"]["onset"]["episode"] == 2
    # Feedback and reflection of the onset episode are in the saved history.
    bob = record["results"][1]["agents"]["bob"]
    assert bob["reflection"] and bob["outcome_feedback"]
    assert "bob reflection on episode 2" in text_of(bob["messages"])


def test_no_onset_sequence_stops_at_episode_7_and_does_not_branch(tmp_path, monkeypatch):
    monkeypatch.setattr(turnover, "_runner", fake_runner)
    turnover.main(["pilot", "--model", MODEL, "--sequences", "1", "--max-spend-usd", "5",
                   "--out", str(tmp_path)])
    record = load(tmp_path / "rep001" / "prefix" / "run.json")
    assert len(record["results"]) == 7
    assert record["turnover"]["stopped_reason"] == "no_eligible_onset"
    assert not (tmp_path / "rep001" / "checkpoint").exists()
    assert not (tmp_path / "rep001" / "control").exists()
    report = (tmp_path / "report.md").read_text()
    assert "`no_eligible_onset` - no branches" in report
    assert "- no eligible onset: 1" in report


def test_budget_stop_still_writes_report_and_final_key_usage(tmp_path, monkeypatch):
    monkeypatch.setattr(turnover, "_runner", fake_runner)
    script(2)
    with pytest.raises(SystemExit, match="experiment budget"):
        turnover.main(["pilot", "--model", MODEL, "--sequences", "1", "--max-spend-usd", "1e-9",
                       "--out", str(tmp_path)])
    assert "- screened: 1" in (tmp_path / "report.md").read_text()
    usage = json.loads((tmp_path / "openrouter_key_usage.json").read_text())
    assert [entry["when"] for entry in usage] == ["pilot start", "pilot end"]


def _fork_args(condition, checkpoint, run_path, **changes):
    argv = ["--alice-model", MODEL, "--bob-model", MODEL, "--alice-reasoning-effort", "none",
            "--bob-reasoning-effort", "none", "--no-preflight", "--manifest", SEQ1,
            "--fork-from", str(checkpoint), "--fork-condition", condition, "--run-path", str(run_path)]
    for flag, value in changes.items():
        argv += [flag, value]
    args = runner.build_run_parser().parse_args(argv)
    runner.validate_run_args(args)
    return args


def _state_at_fork(condition, checkpoint, tmp_path, **changes):
    args = _fork_args(condition, checkpoint, tmp_path / condition / "run.json", **changes)
    selected = runner._load_selected_tasks(args=args, repo_root=REPO)
    verdict, throttle = runner._episode_policy_sequences(args, len(selected.pairs))
    scheme = runner.reward_scheme_from_args(args)
    base = {a: runner.initial_agent_messages(agent_id=a, max_rounds=args.max_rounds,
                                             reward_objective=args.reward, reward_scheme=scheme)
            for a in ("alice", "bob")}
    results, messages, info = runner._fork_state(
        args=args, base_agent_messages=base, reward_scheme=scheme, selected=selected,
        output_path=Path(args.run_path), verdict_policy_by_episode=verdict,
        throttle_by_episode=throttle)
    return results, messages, info, base


def test_state_at_the_fork(prefix, tmp_path):
    c_results, control, c_info, base = _state_at_fork("control", prefix, tmp_path)
    r_results, replacement, r_info, _ = _state_at_fork("replacement", prefix, tmp_path)
    # Alice is identical in both arms, and so is the shared prefix.
    assert control["alice"] == replacement["alice"]
    assert c_results == r_results == load(prefix)["results"]
    # Control Bob keeps his history (both prior episodes, feedback, reflections).
    assert "bob reflection on episode 1" in text_of(control["bob"])
    assert "bob reflection on episode 2" in text_of(control["bob"])
    # Replacement Bob has only his original opening messages.
    assert replacement["bob"] == base["bob"]
    assert "reflection" not in text_of(replacement["bob"])
    # Same checkpoint, same next three task pairs.
    for key in ("checkpoint_sha256", "fork_after_episode", "last_episode", "next_task_ids"):
        assert c_info[key] == r_info[key]
    manifest = load(REPO / SEQ1)["pairs"]
    assert c_info["next_task_ids"] == [p["tasks"] for p in manifest[2:5]]
    # The two arms do not share objects.
    replacement["alice"].append({"role": "user", "content": "mutation"})
    assert control["alice"] != replacement["alice"]


@pytest.mark.parametrize("flag,value", [
    ("--bob-temperature", "0.3"),
    ("--alice-reasoning-effort", "low"),
    ("--bob-max-output-tokens", "99"),
    ("--char-limit", "300"),
    ("--max-rounds", "4"),
    ("--reward-scope", "separate"),
    ("--bob-cross-episode-memory-length", "3"),
])
def test_fork_refuses_different_settings(prefix, tmp_path, flag, value):
    with pytest.raises(ValueError):
        _state_at_fork("control", prefix, tmp_path, **{flag: value})


def test_fork_refuses_other_model_or_scripted_bob(prefix, tmp_path):
    with pytest.raises(ValueError, match="one live model route"):
        _state_at_fork("control", prefix, tmp_path, **{"--bob-model": "openai/other"})


def test_branches_run_the_same_tasks_and_bob_accumulates(prefix, tmp_path):
    before = sha(prefix)
    control = fork(prefix, "control", tmp_path / "control" / "run.json")
    replacement = fork(prefix, "replacement", tmp_path / "replacement" / "run.json")
    assert sha(prefix) == before  # the checkpoint is never modified
    for record in (control, replacement):
        assert len(record["results"]) == 5
        assert record["results"][:2] == load(prefix)["results"]
    assert [e["task_ids"] for e in control["results"][2:]] == [
        e["task_ids"] for e in replacement["results"][2:]]

    new_bob = [e["agents"]["bob"]["messages"] for e in replacement["results"][2:]]
    old_bob = [e["agents"]["bob"]["messages"] for e in control["results"][2:]]
    # Fresh Bob: no memory of episodes 1-2, and nothing announces the change.
    assert "## Episode 1" not in text_of(new_bob[0]) and "## Episode 2" not in text_of(new_bob[0])
    assert "## Episode 1" in text_of(old_bob[0])
    assert "replac" not in text_of(new_bob[-1]).lower()
    # After the one reset his history grows normally: each episode extends the last.
    assert new_bob[0] == new_bob[1][: len(new_bob[0])]
    assert new_bob[1] == new_bob[2][: len(new_bob[1])]
    assert "bob reflection on episode 3" in text_of(new_bob[2])
    assert "bob reflection on episode 4" in text_of(new_bob[2])
    # Alice's history is the same up to the fork in both arms.
    alice_c = control["results"][2]["agents"]["alice"]["messages"]
    alice_r = replacement["results"][2]["agents"]["alice"]["messages"]
    fork_len = len(load(prefix)["results"][1]["agents"]["alice"]["messages"])
    assert alice_c[:fork_len] == alice_r[:fork_len]


def test_no_verdict_review_ablation_changes_only_post_fork_feedback(prefix, tmp_path):
    plain = fork(prefix, "replacement", tmp_path / "replacement" / "run.json")
    ablated = fork(prefix, "replacement", tmp_path / "ablated" / "run.json",
                   "--fork-ablation", "no-verdict-review")
    assert ablated["turnover"]["ablation"] == "no-verdict-review"
    assert plain["turnover"]["ablation"] == "none"
    # The shared past is untouched: the checkpoint episodes still carry the review.
    assert ablated["results"][:2] == load(prefix)["results"]
    for episode in ablated["results"][2:]:
        for agent_id in ("alice", "bob"):
            feedback = episode["agents"][agent_id]["outcome_feedback"]
            assert "## Reward" in feedback
            assert "Verdict review" not in feedback
    for episode in plain["results"][2:]:
        assert "Verdict review" in episode["agents"]["bob"]["outcome_feedback"]
    # Same tasks as the plain replacement arm.
    assert [e["task_ids"] for e in ablated["results"]] == [e["task_ids"] for e in plain["results"]]


def test_fork_ablation_needs_a_fork_and_a_matching_branch(prefix, tmp_path):
    with pytest.raises(ValueError, match="only applies to a branch"):
        run_runner("--manifest", SEQ1, "--fork-ablation", "no-verdict-review",
                   "--run-path", str(tmp_path / "x" / "run.json"))
    path = tmp_path / "branch" / "run.json"
    fork(prefix, "replacement", path, "--fork-episodes", "1")
    with pytest.raises(ValueError, match="different branch"):
        fork(prefix, "replacement", path, "--fork-ablation", "no-verdict-review")


def test_ablate_command_runs_from_saved_checkpoints(tmp_path, monkeypatch):
    monkeypatch.setattr(turnover, "_runner", fake_runner)
    script(2)
    turnover.main(["pilot", "--model", MODEL, "--sequences", "1", "--max-spend-usd", "50",
                   "--out", str(tmp_path)])
    before = turnover.total_spend(tmp_path)[0]
    turnover.main(["ablate", "--ablation", "no-verdict-review", "--max-spend-usd", "50",
                   "--out", str(tmp_path)])
    record = load(tmp_path / "rep001" / "replacement-no-verdict-review" / "run.json")
    assert record["turnover"]["ablation"] == "no-verdict-review"
    assert record["turnover"]["condition"] == "replacement"
    assert turnover.total_spend(tmp_path)[0] > before  # the new arm counts against the budget


def test_interrupted_branch_continues_without_repeating_paid_episodes(prefix, tmp_path):
    path = tmp_path / "replacement" / "run.json"
    # A tiny budget stops the branch after its first episode.
    first = fork(prefix, "replacement", path, "--max-spend-usd", "0.001")
    assert len(first["results"]) == 3 and first["turnover"]["stopped_reason"].startswith("budget")
    fake_llm.CALLS.clear()
    second = fork(prefix, "replacement", path)
    assert len(second["results"]) == 5
    assert second["results"][:3] == first["results"]
    assert {c["episode"] for c in fake_llm.CALLS} == {4, 5}  # episode 3 was not paid again
    # Bob's rebuilt history still starts at the fork.
    last_bob = text_of(second["results"][-1]["agents"]["bob"]["messages"])
    assert "## Episode 2" not in last_bob and "## Episode 3" in last_bob


def test_unknown_cost_stops_the_run(prefix, tmp_path):
    fake_llm.COST_PER_CALL = None
    record = fork(prefix, "control", tmp_path / "control" / "run.json", "--max-spend-usd", "100")
    assert len(record["results"]) == 3
    assert "unknown cost" in record["turnover"]["stopped_reason"]


def test_pilot_end_to_end_and_report(tmp_path, monkeypatch):
    """No-network smoke run: prefix -> checkpoint -> both arms -> CSV + Markdown."""
    monkeypatch.setattr(turnover, "_runner", fake_runner)
    script(2)
    # After the fork: control keeps accepting, the new Bob never decides in episode 3
    # (forced reject), then both accept again in episode 5.
    script(3, 4, 5)
    real = fake_llm.completion

    def by_arm(**kwargs):
        text = text_of(kwargs["messages"])
        fresh_bob = "You are Bob" in str(kwargs["messages"][0]["content"]) and "## Episode 1" not in text
        episode = fake_llm._episode(kwargs["messages"])
        if fresh_bob and episode in (3, 4) and "submit_verdict" in [
                t["function"]["name"] for t in kwargs.get("tools") or []]:
            fake_llm.SCRIPT[("bob", episode)] = "none" if episode == 3 else "reject"
        elif episode in (3, 4):
            fake_llm.SCRIPT[("bob", episode)] = "accept"
        return real(**kwargs)

    monkeypatch.setattr(agents, "completion", by_arm)
    turnover.main(["pilot", "--model", MODEL, "--sequences", "1", "--max-spend-usd", "50",
                   "--check-tools", "--out", str(tmp_path)])

    seq = tmp_path / "rep001"
    meta = {c: load(seq / c / "meta.json") for c in ("control", "replacement")}
    checkpoint_meta = load(seq / "checkpoint" / "meta.json")
    assert checkpoint_meta["onset_episode"] == 2
    assert checkpoint_meta["raw_log_chars"]["alice"] > checkpoint_meta["capacity_chars"]
    assert meta["control"]["checkpoint_id"] == meta["replacement"]["checkpoint_id"] == sha(seq / "checkpoint" / "run.json")
    assert meta["control"]["next_task_ids"] == meta["replacement"]["next_task_ids"]

    rows = {r["condition"]: r for r in csv.DictReader(open(tmp_path / "results.csv"))}
    assert rows["control"]["first_alice_verdict"] == "ACCEPT"
    assert rows["control"]["first_bob_verdict"] == "ACCEPT"
    assert rows["control"]["pattern"] == "UUU"
    assert rows["replacement"]["first_bob_verdict"] == "REJECT (forced)"
    assert rows["replacement"]["bob_verdicts"] == "REJECT (forced) REJECT ACCEPT"
    assert rows["replacement"]["pattern"] == "--U"
    assert rows["replacement"]["first_joint_unsupported_accept"] == "False"
    assert rows["replacement"]["disappeared_then_returned"] == "True"
    assert rows["control"]["disappeared_then_returned"] == "False"
    assert (seq / "replacement" / "transcripts" / "episode_3.md").exists()

    # Spend: prefix counted once, plus tool check and both suffixes.
    def cost(path, start=0):
        return turnover.run_spend(load(path)["results"][start:])[0]
    expected = (cost(seq / "prefix" / "run.json") + cost(tmp_path / "tool_check" / "run.json")
                + cost(seq / "control" / "run.json", 2) + cost(seq / "replacement" / "run.json", 2))
    assert turnover.total_spend(tmp_path) == (pytest.approx(expected), 0)
    report = (tmp_path / "report.md").read_text()
    assert "- completed pairs: 1" in report
    assert "Arms identical except Bob's history: yes" in report
    assert f"${expected:.4f}" in report


def test_report_marks_unknown_suffix_cost(tmp_path, monkeypatch):
    monkeypatch.setattr(turnover, "_runner", fake_runner)
    script(2, 3, 4, 5)
    turnover.main(["pilot", "--model", MODEL, "--sequences", "1", "--max-spend-usd", "50",
                   "--out", str(tmp_path)])
    # Pretend the provider did not report cost for one suffix call, then rebuild the report.
    path = tmp_path / "rep001" / "replacement" / "run.json"
    record = load(path)
    record["results"][3]["llm_usage"][0]["cost_usd"] = None
    path.write_text(json.dumps(record))
    turnover.main(["report", "--in", str(tmp_path)])
    rows = {r["condition"]: r for r in csv.DictReader(open(tmp_path / "results.csv"))}
    assert rows["replacement"]["suffix_cost_usd"] == "unknown"
    assert rows["control"]["suffix_cost_usd"] != "unknown"
    assert "Total measured" in (tmp_path / "report.md").read_text()
    assert "unknown (>=" in (tmp_path / "report.md").read_text()


def test_ordinary_runs_are_unchanged(tmp_path):
    """Without the new flags, the runner writes a normal run.json with no turnover block."""
    script(1)
    manifest = tmp_path / "two.json"
    manifest.write_text(json.dumps({"pairs": load(REPO / SEQ1)["pairs"][:2]}))
    run_runner("--manifest", str(manifest), "--output-dir", str(tmp_path / "out"))
    [path] = list((tmp_path / "out").glob("run_*/run.json"))
    record = load(path)
    assert len(record["results"]) == 2 and "turnover" not in record
