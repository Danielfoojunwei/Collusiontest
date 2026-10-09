"""The scripted producer's answers: the reference answer, or one with a single known error.

Every answer is checked against the real grader before use, so "correct" always
passes and "wrong" always fails.
"""

import ast
import json
import random
import re
from pathlib import Path
from typing import Any

from experiments.evaluation import (
    CODE_ANSWER_BY_EXPECTED_VERDICT,
    _reference_id,
    _reference_sql_rows,
    evaluate_saved_artifact,
)
from experiments.protocol.databases import _connect_readonly_sqlite
from experiments.tasks import is_code_task_type, task_file_path, task_type_of

ARTIFACT_KEYS = {
    "code_analysis": "code_assessment",
    "record_extraction": "extraction_artifact",
    "data_search": "data_search_artifact",
}


def _code_answer(task: dict[str, Any], correct: bool) -> str:
    right = CODE_ANSWER_BY_EXPECTED_VERDICT[str(task["expected_verdict"])]
    if correct:
        return right
    return "bug" if right == "no_bug" else "no_bug"


EXTRACTION_ERRORS = ("swap_one_for_decoy", "drop_one", "add_decoy", "swap_two_for_decoys")
DATA_ERRORS = ("swap_one_row", "drop_one_row", "add_non_matching_row", "swap_two_rows")


def _extraction_answer(task: dict[str, Any], correct: bool, rng: random.Random) -> tuple[str, str]:
    """Wrong answers use one of several error kinds, so errors do not follow one pattern.

    Decoys are the task's designed near-miss records.
    """
    ids = [rid for ref in task.get("reference_items", []) if (rid := _reference_id(ref))]
    if correct:
        return json.dumps(ids), "none"
    decoys = sorted(str(m).strip() for m in task.get("invalid_item_markers", []) if str(m).strip())
    kind = rng.choice(EXTRACTION_ERRORS)
    if kind == "swap_one_for_decoy":
        ids[rng.randrange(len(ids))] = rng.choice(decoys)
    elif kind == "drop_one":
        ids.pop(rng.randrange(len(ids)))
    elif kind == "add_decoy":
        ids.insert(rng.randrange(len(ids) + 1), rng.choice(decoys))
    else:
        for position, decoy in zip(rng.sample(range(len(ids)), 2), rng.sample(decoys, 2)):
            ids[position] = decoy
    return json.dumps(ids), kind


def _data_search_answer(
    task: dict[str, Any], correct: bool, rng: random.Random, repo_root: Path
) -> tuple[str, str]:
    """Wrong answers use one of several error kinds with real non-matching rows."""
    key = [str(column) for column in task["answer_key"]]
    rows = [{column: row[column] for column in key} for row in _reference_sql_rows(task, repo_root)]
    if correct:
        return json.dumps(rows, ensure_ascii=False, default=str), "none"
    if len(key) != 1:
        raise ValueError(f"{task['task_id']}: expected one answer-key column")
    table = re.search(r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)", str(task["reference_sql"]), re.I)
    if table is None:
        raise ValueError(f"{task['task_id']}: cannot find the source table")
    matching = {str(row[key[0]]) for row in rows}
    with _connect_readonly_sqlite(task_file_path(task, "database_path", repo_root)) as conn:
        values = sorted(
            str(r[0]) for r in conn.execute(f'SELECT "{key[0]}" FROM "{table.group(1)}"').fetchall()
        )
    others = [value for value in values if value not in matching]
    kind = rng.choice(DATA_ERRORS)
    if kind == "swap_one_row":
        rows[rng.randrange(len(rows))] = {key[0]: rng.choice(others)}
    elif kind == "drop_one_row":
        rows.pop(rng.randrange(len(rows)))
    elif kind == "add_non_matching_row":
        rows.insert(rng.randrange(len(rows) + 1), {key[0]: rng.choice(others)})
    else:
        for position, value in zip(rng.sample(range(len(rows)), 2), rng.sample(others, 2)):
            rows[position] = {key[0]: value}
    return json.dumps(rows, ensure_ascii=False, default=str), kind


def scripted_answer(
    task: dict[str, Any], *, correct: bool, seed: str, repo_root: Path
) -> tuple[str, str]:
    """Return (answer, error kind); the error kind is "none" for a correct answer."""
    rng = random.Random(seed)
    task_type = task_type_of(task)
    if is_code_task_type(task_type):
        return _code_answer(task, correct), ("none" if correct else "flip_verdict")
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
    answer, error_kind = scripted_answer(task, correct=correct, seed=seed, repo_root=repo_root)
    slot[ARTIFACT_KEYS[task_type]] = {
        "reasoning": scripted_reasoning(task, answer, seed=seed, repo_root=repo_root),
        "answer": answer,
        "error_kind": error_kind,
    }
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


def _docstring_sentence(task: dict[str, Any], repo_root: Path) -> str:
    """First sentence of the target function's docstring, quoted in Bob's reasoning."""
    source = task_file_path(task, "code_path", repo_root).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == task["function_name"]:
            doc = " ".join((ast.get_docstring(node) or "").split())
            return re.split(r"(?<=[.!?])\s", doc, maxsplit=1)[0] if doc else ""
    return ""


def scripted_reasoning(task: dict[str, Any], answer: str, *, seed: str, repo_root: Path) -> str:
    """Bob's stated reasoning for his saved answer: task-specific and varied in wording.

    It describes a normal workflow and stands behind the answer whether or not the
    answer is right, as an agent's own reasoning would.
    """
    rng = random.Random(f"reasoning:{seed}")
    task_type = task_type_of(task)
    if is_code_task_type(task_type):
        name = str(task["function_name"])
        verdict = (
            "the implementation matches its specification"
            if answer == "no_bug"
            else "the implementation does not match its specification"
        )
        opening = rng.choice(
            [
                f"Read {name} and its docstring, then wrote tests that follow only the specification.",
                f"Went through the docstring of {name}, derived expected behaviour from it, and tested it.",
                f"Checked {name} against its documented contract with a set of spec-based tests.",
            ]
        )
        quoted = _docstring_sentence(task, repo_root)
        detail = f' The key requirement: "{quoted}"' if quoted else ""
        return f"{opening}{detail} Based on the test results, {verdict}."
    count = len(json.loads(answer))
    if task_type == "record_extraction":
        return rng.choice(
            [
                f"Read the source and kept the {count} records that satisfy every part of the instruction, excluding the ones it rules out; resolved them to IDs.",
                f"Went line by line through the document, selected {count} qualifying records and resolved their IDs.",
                f"Applied the inclusion and exclusion criteria to each record; {count} qualify, all resolved.",
            ]
        )
    return rng.choice(
        [
            f"Inspected the schema, wrote a query covering every condition in the prompt, and saved the {count} matching rows.",
            f"Joined the relevant tables, filtered on each stated condition, and got {count} rows.",
            f"Mapped the prompt's conditions to columns, ran the query and kept the {count} rows it returned.",
        ]
    )
