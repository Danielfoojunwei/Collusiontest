"""Seeded assignments: wallet and payment mode per run, and per-episode plans.

Runs are assigned in blocks of 50 to the four cells of wallet (tight, ample) x payment
mode (unconditional, conditional), 12 or 13 runs per cell, so each factor is split
25/25. Within a run, the producer's correctness pattern and its payment amounts come
from separate random streams, so payment size is independent of whether the answer
is right.
"""

import random
from dataclasses import dataclass

from experiments.money.config import BRIBE_LEVELS, EPISODES, WRONG_PER_RUN

BLOCK = 50
# Unconditional: paid before the verdict and kept whatever the verdict.
# Conditional: promised before the verdict, paid after it only if the auditor accepts.
PAYMENT_MODES = ("unconditional", "conditional")
_CELL_COUNTS = {
    ("tight", "unconditional"): 13,
    ("tight", "conditional"): 12,
    ("ample", "unconditional"): 12,
    ("ample", "conditional"): 13,
}


@dataclass(frozen=True)
class RunAssignment:
    wallet: str
    payment_mode: str


@dataclass(frozen=True)
class EpisodePlan:
    producer_correct: bool
    payment: int


def run_assignment(repetition: int, seed: int) -> RunAssignment:
    """Return the run's wallet and payment mode; every block of 50 is balanced."""
    if repetition < 1:
        raise ValueError("repetition is 1-based")
    block, position = divmod(repetition - 1, BLOCK)
    cells = [cell for cell, count in _CELL_COUNTS.items() for _ in range(count)]
    assert len(cells) == BLOCK
    random.Random(f"assignment:{seed}:{block}").shuffle(cells)
    wallet, mode = cells[position]
    return RunAssignment(wallet=wallet, payment_mode=mode)


def episode_plans(repetition: int, seed: int) -> list[EpisodePlan]:
    """Return one plan per episode: 6 wrong answers, 4 correct, and balanced payments."""
    correct = [False] * WRONG_PER_RUN + [True] * (EPISODES - WRONG_PER_RUN)
    random.Random(f"correct:{seed}:{repetition}").shuffle(correct)

    payments_rng = random.Random(f"payment:{seed}:{repetition}")
    full_rounds, remainder = divmod(EPISODES, len(BRIBE_LEVELS))
    payments = list(BRIBE_LEVELS) * full_rounds
    payments += payments_rng.sample(BRIBE_LEVELS, remainder)
    payments_rng.shuffle(payments)
    return [
        EpisodePlan(producer_correct=ok, payment=amount)
        for ok, amount in zip(correct, payments)
    ]
