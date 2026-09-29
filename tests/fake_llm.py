"""A tiny scripted stand-in for litellm.completion, so tests make no network calls.

It looks at which tools the runner offers to work out the phase, then answers:
task phase -> read the task input once, then save an answer;
communication -> send a short (<200 char) message; verdict -> submit a verdict;
reflection (no tool_choice) -> plain text.
"""

import itertools
import json
import re

import litellm

# SCRIPT[(agent, episode_number)] = "accept" / "reject" / "none" (never submits -> forced)
SCRIPT: dict[tuple[str, int], str] = {}
DEFAULT_VERDICT = "reject"
# Cost reported per call; None means the provider did not report one.
COST_PER_CALL: float | None = 0.001
MESSAGES: dict[tuple[str, int], str] = {}
CALLS: list[dict] = []
_ids = itertools.count()

READ_TOOL = {"read_code": {}, "read_source": {}, "inspect_database": {}}


def _agent(messages) -> str:
    return "alice" if "You are Alice" in str(messages[0].get("content")) else "bob"


def _episode(messages) -> int:
    numbers = re.findall(r"## Episode (\d+)", " ".join(str(m.get("content")) for m in messages))
    return int(numbers[-1]) if numbers else 0


def _tool_call(name, arguments):
    return {"id": f"call_{next(_ids)}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)}}


def _answer(tools):
    for tool in tools:
        fn = tool["function"]
        if fn["name"] == "save_final_answer":
            schema = fn["parameters"]["properties"]["answer"]
            if schema.get("enum"):
                return schema["enum"][0]
            if schema.get("type") == "array":
                return []
            return "x"
    return "x"


def completion(*, model, messages, tools=None, tool_choice=None, **kwargs):
    agent, episode = _agent(messages), _episode(messages)
    names = [t["function"]["name"] for t in tools or []]
    CALLS.append({"agent": agent, "episode": episode, "tools": names, "tool_choice": tool_choice})
    message = {"role": "assistant", "content": None}
    if tool_choice is None:
        message["content"] = f"{agent} reflection on episode {episode}."
    elif "submit_verdict" in names:
        verdict = SCRIPT.get((agent, episode), DEFAULT_VERDICT)
        if verdict == "none":
            message["content"] = "I will not decide."
        else:
            message["tool_calls"] = [_tool_call("submit_verdict", {"reasoning": "scripted", "verdict": verdict})]
    elif "send_message" in names:
        text = MESSAGES.get((agent, episode), f"{agent}: my work is done, looks fine.")
        message["tool_calls"] = [_tool_call("send_message", {"content": text[:200]})]
    else:
        already_read = any(
            call.get("function", {}).get("name") in READ_TOOL
            for m in messages[-6:] for call in (m.get("tool_calls") or [])
        )
        read = next((n for n in names if n in READ_TOOL), None)
        if read and not already_read:
            message["tool_calls"] = [_tool_call(read, READ_TOOL[read])]
        else:
            message["tool_calls"] = [_tool_call("save_final_answer", {"reasoning": "scripted", "answer": _answer(tools)})]
    response = litellm.ModelResponse(
        model=model,
        choices=[{"index": 0, "message": message,
                  "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}],
        usage={"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
    )
    response._hidden_params["response_cost"] = COST_PER_CALL
    return response
