"""The scripted producer's answers: the reference answer, or one with a single known error.

Every answer is checked against the real grader before use, so "correct" always
passes and "wrong" always fails.
"""

import json
import random
from pathlib import Path
from typing import Any

from experiments.evaluation import (
    CODE_ANSWER_BY_EXPECTED_VERDICT,
    _reference_id,
    _reference_sql_rows,
    evaluate_saved_artifact,
)
from experiments.tasks import is_code_task_type, task_type_of

ARTIFACT_KEYS = {
    "code_analysis": "code_assessment",
    "record_extraction": "extraction_artifact",
    "data_search": "data_search_artifact",
}
SCRIPTED_REASONING = "Completed the task with the provided tools and saved the final answer."


def _code_answer(task: dict[str, Any], correct: bool) -> str:
    right = CODE_ANSWER_BY_EXPECTED_VERDICT[str(task["expected_verdict"])]
    if correct:
        return right
    return "bug" if right == "no_bug" else "no_bug"


def _extraction_answer(task: dict[str, Any], correct: bool, rng: random.Random) -> str:
    ids = [rid for ref in task.get("reference_items", []) if (rid := _reference_id(ref))]
    if not correct:
        ids.pop(rng.randrange(len(ids)))
    return json.dumps(ids)


def _data_search_answer(
    task: dict[str, Any], correct: bool, rng: random.Random, repo_root: Path
) -> str:
    key = [str(column) for column in task["answer_key"]]
    rows = [{column: row[column] for column in key} for row in _reference_sql_rows(task, repo_root)]
    if not correct:
        rows.pop(rng.randrange(len(rows)))
    return json.dumps(rows, ensure_ascii=False, default=str)


def scripted_answer(
    task: dict[str, Any], *, correct: bool, seed: str, repo_root: Path
) -> str:
    rng = random.Random(seed)
    task_type = task_type_of(task)
    if is_code_task_type(task_type):
        return _code_answer(task, correct)
    if task_type == "record_extraction":
        return _extraction_answer(task, correct, rng)
    if task_type == "data_search":
        return _data_search_answer(task, correct, rng, repo_root)
    raise ValueError(f"Unknown task_type: {task_type}")


def install_scripted_answer(
    *,
    task: dict[str, Any],
    slot: dict[str, Any],
    correct: bool,
    seed: str,
    repo_root: Path,
) -> str:
    """Save the scripted answer into the producer's slot and verify it grades as planned."""
    task_type = task_type_of(task)
    answer = scripted_answer(task, correct=correct, seed=seed, repo_root=repo_root)
    slot[ARTIFACT_KEYS[task_type]] = {"reasoning": SCRIPTED_REASONING, "answer": answer}
    slot["final_answer_saved"] = True
    # Grade a copy: the code grader deletes the slot's scratch directory.
    probe = dict(slot, task_tmp_dir="")
    graded = evaluate_saved_artifact(
        task=task, task_type=task_type, slot=probe, repo_root=repo_root
    ).expected_verdict
    if graded != ("pass" if correct else "fail"):
        raise AssertionError(
            f"scripted answer for {task['task_id']} graded {graded}, planned "
            f"{'correct' if correct else 'wrong'}"
        )
    return answer
