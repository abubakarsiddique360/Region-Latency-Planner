"""Problem definition for the region planner: candidate regions, clients, and RTTs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_TARGET_MS = 100.0


class ProblemError(ValueError):
    """Raised when a problem description cannot be used."""


@dataclass(frozen=True)
class Region:
    name: str
    cost: float = 0.0


@dataclass(frozen=True)
class Client:
    name: str
    weight: float
    rtt: Mapping[str, float]


@dataclass(frozen=True)
class Assignment:
    client: str
    region: str
    rtt: float
    weight: float


@dataclass(frozen=True)
class Problem:
    name: str
    regions: tuple[Region, ...]
    clients: tuple[Client, ...]
    target_ms: float = DEFAULT_TARGET_MS

    @property
    def region_names(self) -> tuple[str, ...]:
        return tuple(region.name for region in self.regions)

    @property
    def total_weight(self) -> float:
        return sum(client.weight for client in self.clients)

    def cost_of(self, names: tuple[str, ...]) -> float:
        index = {region.name: region.cost for region in self.regions}
        return sum(index[name] for name in names)


def problem_from_dict(payload: Mapping[str, Any]) -> Problem:
    if not isinstance(payload, Mapping):
        raise ProblemError("problem must be a JSON object")

    raw_regions = payload.get("regions")
    if not isinstance(raw_regions, list) or not raw_regions:
        raise ProblemError("regions must be a non-empty list")

    regions: list[Region] = []
    seen_regions: set[str] = set()
    for entry in raw_regions:
        if isinstance(entry, str):
            entry = {"name": entry}
        if not isinstance(entry, Mapping) or not entry.get("name"):
            raise ProblemError("every region needs a name")
        name = str(entry["name"])
        if name in seen_regions:
            raise ProblemError(f"duplicate region {name!r}")
        seen_regions.add(name)
        cost = float(entry.get("cost", 0.0))
        if cost < 0:
            raise ProblemError(f"region {name!r} has a negative cost")
        regions.append(Region(name=name, cost=cost))

    raw_clients = payload.get("clients")
    if not isinstance(raw_clients, list) or not raw_clients:
        raise ProblemError("clients must be a non-empty list")

    clients: list[Client] = []
    seen_clients: set[str] = set()
    for entry in raw_clients:
        if not isinstance(entry, Mapping) or not entry.get("name"):
            raise ProblemError("every client needs a name")
        name = str(entry["name"])
        if name in seen_clients:
            raise ProblemError(f"duplicate client {name!r}")
        seen_clients.add(name)
        weight = float(entry.get("weight", 1.0))
        if weight <= 0:
            raise ProblemError(f"client {name!r} needs a positive weight")
        raw_rtt = entry.get("rtt")
        if not isinstance(raw_rtt, Mapping):
            raise ProblemError(f"client {name!r} needs an rtt map")
        rtt: dict[str, float] = {}
        for region in regions:
            if region.name not in raw_rtt:
                raise ProblemError(f"client {name!r} is missing rtt to {region.name!r}")
            value = float(raw_rtt[region.name])
            if value < 0:
                raise ProblemError(f"client {name!r} has a negative rtt")
            rtt[region.name] = value
        unknown = set(raw_rtt) - {region.name for region in regions}
        if unknown:
            raise ProblemError(f"client {name!r} references unknown regions: {sorted(unknown)}")
        clients.append(Client(name=name, weight=weight, rtt=rtt))

    target = float(payload.get("target_ms", DEFAULT_TARGET_MS))
    if target <= 0:
        raise ProblemError("target_ms must be positive")

    return Problem(
        name=str(payload.get("name", "network")),
        regions=tuple(regions),
        clients=tuple(clients),
        target_ms=target,
    )


def load_problem(path: Path | str) -> Problem:
    source = Path(path)
    if not source.exists():
        raise ProblemError(f"file not found: {source}")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProblemError(f"not valid JSON at line {exc.lineno}: {exc.msg}") from exc
    return problem_from_dict(payload)
