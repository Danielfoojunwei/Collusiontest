"""Append-only credit ledger for both agents; balances are derived, never stored."""

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from experiments.money.config import AGENT, PRODUCER

KINDS = (
    "start",
    "tool_cost",
    "reflection_read",
    "transfer_out",
    "transfer_in",
    "accept_pay",
    "accuracy_pay",
)


class InsufficientCredits(Exception):
    """A charge would take a balance below zero."""


@dataclass(frozen=True)
class Entry:
    agent: str
    episode: int
    phase: str
    kind: str
    amount: int
    note: str = ""


class Ledger:
    def __init__(self, entries: Iterable[Entry] = ()) -> None:
        self.entries: list[Entry] = list(entries)

    @classmethod
    def opened(cls, starts: dict[str, int]) -> "Ledger":
        ledger = cls()
        for agent, amount in starts.items():
            ledger._add(Entry(agent, 0, "setup", "start", amount))
        return ledger

    @classmethod
    def from_records(cls, records: list[dict[str, Any]]) -> "Ledger":
        return cls(Entry(**record) for record in records)

    def records(self) -> list[dict[str, Any]]:
        return [asdict(entry) for entry in self.entries]

    def balance(self, agent: str) -> int:
        return sum(entry.amount for entry in self.entries if entry.agent == agent)

    def _add(self, entry: Entry) -> None:
        if entry.kind not in KINDS:
            raise ValueError(f"Unknown ledger kind: {entry.kind}")
        self.entries.append(entry)

    def charge(self, agent: str, episode: int, phase: str, kind: str, cost: int, note: str = "") -> None:
        if cost < 0:
            raise ValueError("cost must be non-negative")
        if self.balance(agent) < cost:
            raise InsufficientCredits(
                f"this costs {cost} credits and your balance is {self.balance(agent)}"
            )
        self._add(Entry(agent, episode, phase, kind, -cost, note))

    def credit(self, agent: str, episode: int, phase: str, kind: str, amount: int, note: str = "") -> None:
        if amount < 0:
            raise ValueError("amount must be non-negative")
        self._add(Entry(agent, episode, phase, kind, amount, note))

    def transfer(self, sender: str, recipient: str, episode: int, phase: str, amount: int) -> None:
        if sender == recipient or {sender, recipient} != {AGENT, PRODUCER}:
            raise ValueError("transfers go between the two agents")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 1:
            raise ValueError("amount must be a positive whole number of credits")
        self.charge(sender, episode, phase, "transfer_out", amount, note=recipient)
        self.credit(recipient, episode, phase, "transfer_in", amount, note=sender)

    def episode_entries(self, episode: int) -> list[Entry]:
        return [entry for entry in self.entries if entry.episode == episode]
