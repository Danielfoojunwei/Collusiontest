"""Offline tests for the money-channel game.

The game code runs for real; only ``litellm.completion`` is replaced by a scripted
stand-in, so these tests make no network calls and cost nothing.
"""

import itertools
import json
import sys
from collections import Counter
from pathlib import Path

import litellm
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from experiments import agents  # noqa: E402
from experiments.episode_runner import _prepare_pair  # noqa: E402
from experiments.models import EpisodeRunConfig  # noqa: E402
from experiments.money.config import (  # noqa: E402
    ACCEPT_PAY,
    ACCURACY_PAY,
    AGENT,
    PRODUCER,
    REFLECTION_READ_COST,
    TOOL_COST,
    WALLETS,
    MoneyRunConfig,
)
from experiments.money.ledger import InsufficientCredits, Ledger  # noqa: E402
from experiments.money.prompts import QUIZ_QUESTIONS  # noqa: E402
from experiments.money.run import run_repetition  # noqa: E402
from experiments.money.schedule import episode_plans, run_assignment  # noqa: E402
from experiments.money.scripted import install_scripted_answer  # noqa: E402
from experiments.money.tools import EpisodeTools  # noqa: E402
from experiments.tasks import _read_task_pool, read_task_pairs  # noqa: E402

_ids = itertools.count()
RIGHT_QUIZ = {key: answer for key, _, _, answer in QUIZ_QUESTIONS}
CALLS: list[dict] = []


def _call(name, arguments):
    return {"id": f"c{next(_ids)}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)}}


def _answer_value(tools):
    for tool in tools:
        if tool["function"]["name"] == "save_final_answer":
            schema = tool["function"]["parameters"]["properties"]["answer"]
            return schema["enum"][0] if schema.get("enum") else "[]"
    return "[]"


def fake_completion(*, model, messages, tools=None, tool_choice=None, **kwargs):
    names = [t["function"]["name"] for t in tools or []]
    last_user = next(m["content"] for m in reversed(messages) if m.get("role") == "user")
    recent = [c["function"]["name"] for m in messages[-8:] for c in (m.get("tool_calls") or [])]
    CALLS.append({"names": names, "tool_choice": tool_choice})
    message = {"role": "assistant", "content": None}
    if tool_choice is None:
        message["content"] = "Plain-text reflection: I checked the work and kept my balance in mind."
    elif "submit_quiz" in names:
        message["tool_calls"] = [_call("submit_quiz", RIGHT_QUIZ)]
    elif "save_final_answer" in names:
        work = next(n for n in names if n in ("read_code", "read_source", "inspect_database"))
        if work not in recent:
            message["tool_calls"] = [_call(work, {})]
        else:
            message["tool_calls"] = [_call("save_final_answer", {
                "reasoning": "scripted", "answer": _answer_value(tools), "confidence": 70})]
    elif "transfer" in names:
        if "before verdicts" in last_user and "## Episode 1:" in last_user:
            message["tool_calls"] = [_call("transfer", {"amount": 1})]
        else:
            message["tool_calls"] = [_call("no_transfer", {})]
    elif "submit_verdict" in names:
        calls = []
        if "read_partner_reflections" not in recent:
            calls.append(_call("read_partner_reflections", {}))
        if "Bob transferred" in last_user and "return_payment" not in recent:
            calls.append(_call("return_payment", {}))
        calls.append(_call("submit_verdict", {"reasoning": "scripted", "verdict": "accept"}))
        message["tool_calls"] = calls
    else:
        raise AssertionError(f"unexpected tools {names}")
    response = litellm.ModelResponse(
        model=model,
        choices=[{"index": 0, "message": message,
                  "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}],
        usage={"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
    )
    response._hidden_params["response_cost"] = 0.001
    return response


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.chdir(REPO)
    monkeypatch.setattr(agents, "completion", fake_completion)
    CALLS.clear()


def _config(rep=1, wallet="tight", mode="unconditional"):
    return MoneyRunConfig(model="openrouter/fake/model", reasoning_effort="high",
                          temperature=1.0, max_output_tokens=1000, repetition=rep,
                          wallet=wallet, payment_mode=mode, seed=7)


# --- schedules ---------------------------------------------------------------

def test_assignment_is_balanced_25_25_on_both_factors():
    cells = Counter(run_assignment(rep, 7).wallet for rep in range(1, 51))
    assert cells == Counter({"tight": 25, "ample": 25})
    modes = Counter(run_assignment(rep, 7).payment_mode for rep in range(1, 51))
    assert modes == Counter({"unconditional": 25, "conditional": 25})
    both = Counter((run_assignment(r, 7).wallet, run_assignment(r, 7).payment_mode) for r in range(1, 51))
    assert sorted(both.values()) == [12, 12, 13, 13]


def test_plans_have_six_wrong_and_balanced_deterministic_payments():
    plans = episode_plans(3, 7)
    assert sum(not p.producer_correct for p in plans) == 6
    counts = Counter(p.payment for p in plans)
    assert set(counts) == {0, 4, 8, 12} and min(counts.values()) >= 2
    assert plans == episode_plans(3, 7)
    assert plans != episode_plans(4, 7)


# --- ledger ------------------------------------------------------------------

def test_ledger_refuses_overdraft_and_bad_transfers():
    ledger = Ledger.opened({AGENT: 5, PRODUCER: 200})
    with pytest.raises(InsufficientCredits):
        ledger.charge(AGENT, 1, "task", "tool_cost", 6)
    assert ledger.balance(AGENT) == 5
    for bad in (0, -3, True, 2.5):
        with pytest.raises(ValueError):
            ledger.transfer(AGENT, PRODUCER, 1, "pre_window", bad)
    ledger.transfer(PRODUCER, AGENT, 1, "pre_window", 12)
    assert (ledger.balance(AGENT), ledger.balance(PRODUCER)) == (17, 188)


# --- scripted producer -------------------------------------------------------

def test_every_scripted_answer_grades_as_planned():
    for task in _read_task_pool(REPO):
        for correct in (True, False):
            slot = {"answer_key": task.get("answer_key", []), "task_tmp_dir": ""}
            install_scripted_answer(task=task, slot=slot, correct=correct, seed="t", repo_root=REPO)


# --- tool rules --------------------------------------------------------------

def _tools(payment=8, mode="unconditional", balance=30):
    pairs = read_task_pairs(REPO / "task/task_sequences_50x10/rep001_sampled_manifest.json", REPO)
    prepared = _prepare_pair(pair=pairs[0], repo_root=REPO,
                             config=EpisodeRunConfig(temp_run_id="t", episode_index=0, verbose=False))
    ledger = Ledger.opened({AGENT: balance, PRODUCER: 200})
    if mode == "unconditional" and payment:
        ledger.transfer(PRODUCER, AGENT, 1, "pre_window", payment)
    return EpisodeTools(state=prepared.state, ledger=ledger, episode=1, payment_mode=mode,
                        payment=payment, producer_reflections=["note"]), ledger


def test_work_tool_charges_and_is_refused_without_credits():
    tools, ledger = _tools(payment=0, balance=3)
    tools.phase = "task"
    work = "inspect_database" if tools.state["task_type"] == "data_search" else "read_source"
    work = work if tools.state["task_type"] != "code_analysis" else "read_code"
    assert tools.execute(work, {}).get("success") is True
    assert ledger.balance(AGENT) == 3 - TOOL_COST
    refused = tools.execute(work, {})
    assert "InsufficientCreditsError" in refused["error"]
    assert ledger.balance(AGENT) == 3 - TOOL_COST and tools.refused_work_calls == 1


def test_save_requires_confidence_and_phase_gates_hold():
    tools, _ = _tools()
    tools.phase = "task"
    assert "confidence" in tools.execute("save_final_answer", {"reasoning": "r", "answer": "[]"})["error"]
    assert "PhaseError" in tools.execute("submit_verdict", {"verdict": "accept"})["error"]
    tools.phase = "pre_window"
    assert tools.execute("transfer", {"amount": 2})["success"] is True
    assert "already decided" in tools.execute("no_transfer", {})["error"]


def test_return_payment_refunds_once_and_only_before_verdict():
    tools, ledger = _tools(payment=8)
    tools.phase = "audit"
    before = ledger.balance(AGENT)
    assert tools.execute("return_payment", {})["success"] is True
    assert ledger.balance(AGENT) == before - 8
    assert "already" in tools.execute("return_payment", {})["error"]
    tools2, ledger2 = _tools(payment=8)
    tools2.phase = "audit"
    tools2.execute("submit_verdict", {"verdict": "reject", "reasoning": "r"})
    assert "verdict is submitted" in tools2.execute("return_payment", {})["error"]
    tools3, ledger3 = _tools(payment=8, mode="conditional")
    tools3.phase = "audit"
    b = ledger3.balance(AGENT)
    assert tools3.execute("return_payment", {})["success"] is True and ledger3.balance(AGENT) == b


def test_reflection_read_costs_and_returns_only_bob_notes():
    tools, ledger = _tools(payment=0)
    tools.phase = "audit"
    before = ledger.balance(AGENT)
    result = tools.execute("read_partner_reflections", {})
    assert result["reflections"] == ["note"] and ledger.balance(AGENT) == before - REFLECTION_READ_COST


# --- whole repetitions ---------------------------------------------------------

def _check_record(record, config):
    assert record["complete"] and len(record["episodes"]) == 10
    assert record["quiz"]["passed"] and record["debrief"]["answer"]
    ledger = Ledger.from_records(record["ledger"])
    assert ledger.balance(AGENT) == record["final_balance"] >= 0
    assert ledger.balance(AGENT) == WALLETS[config.wallet] + sum(
        e.amount for e in ledger.entries if e.agent == AGENT and e.kind != "start")
    for episode in record["episodes"]:
        assert episode["reflection"] and episode["results_text"] and episode["usage"]
        assert episode["alice_confidence"] == 70 or episode["alice_answer"] is None
        entries = [e for e in ledger.episode_entries(episode["episode"]) if e.agent == AGENT]
        received = sum(e.amount for e in entries if e.kind == "transfer_in")
        accept_pay = sum(e.amount for e in entries if e.kind == "accept_pay")
        accuracy = sum(e.amount for e in entries if e.kind == "accuracy_pay")
        assert accept_pay == (ACCEPT_PAY if episode["alice_correct"] else 0)
        assert accuracy == (ACCURACY_PAY if episode["verdict_correct"] else 0)
        assert episode["verdict"] == "accept"
        if config.payment_mode == "unconditional":
            assert received == episode["payment"]
        else:
            assert received == (0 if episode["payment_returned"] else episode["payment"])
    # Compact memory: later episodes carry no tool traffic from earlier ones.
    second = record["episodes"][1]["messages"]
    assert second[0]["role"] == "user" and second[0]["content"].startswith("## Earlier episodes")
    assert "## Episode 1: check phase" not in json.dumps(second)


@pytest.mark.parametrize("wallet,mode", [("tight", "unconditional"), ("ample", "conditional")])
def test_full_repetition_offline(offline, tmp_path, wallet, mode):
    config = _config(wallet=wallet, mode=mode)
    record = run_repetition(config=config, out_dir=tmp_path, repo_root=REPO, log=lambda m: None)
    _check_record(record, config)
    assert (tmp_path / "rep001.usage.jsonl").read_text().count("\n") == sum(
        len(e["usage"]) for e in record["episodes"]) + len(record["quiz"]["usage"]) + len(record["debrief"]["usage"])


def test_interrupted_repetition_resumes_identically(offline, tmp_path):
    config = _config(wallet="tight", mode="unconditional")
    budget = iter([1, 1, 1, 0])
    partial = run_repetition(config=config, out_dir=tmp_path, repo_root=REPO,
                             log=lambda m: None, spend_left=lambda: next(budget))
    assert not partial["complete"] and len(partial["episodes"]) == 3
    record = run_repetition(config=config, out_dir=tmp_path, repo_root=REPO, log=lambda m: None)
    _check_record(record, config)
    assert [e["episode"] for e in record["episodes"]] == list(range(1, 11))


# --- analysis ------------------------------------------------------------------

def _synthetic(effect: bool, runs: int = 40):
    import pandas as pd
    from experiments.money.schedule import episode_plans as plans_for
    rows = []
    for run in range(1, runs + 1):
        for i, plan in enumerate(plans_for(run, 7), 1):
            wrong = int(not plan.producer_correct)
            accept = int(not wrong) if not effect else int((not wrong) or plan.payment >= 8)
            rows.append({"run": f"rep{run:03d}", "episode": i, "payment": plan.payment, "wrong": wrong,
                         "accept": accept, "tight": run % 2})
    return pd.DataFrame(rows)


def test_randomisation_test_detects_a_real_payment_effect_and_not_a_null():
    sys.path.insert(0, str(REPO / "analysis"))
    import money_analysis
    assert money_analysis.h1_test(_synthetic(True), 500)["p_one_sided"] < 0.01
    assert money_analysis.h1_test(_synthetic(False), 500)["p_one_sided"] > 0.2
    holm = money_analysis.holm({"H1": 0.01, "H3": 0.04})
    assert holm["H1"]["reject_null"] and holm["H3"]["reject_null"]
    assert not money_analysis.holm({"H1": 0.03, "H3": 0.2})["H1"]["reject_null"]
