from __future__ import annotations

from dataclasses import dataclass

from .models import CPURequest, RequestType


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    requests: list[CPURequest]
    initial_memory: dict[int, int]
    read_latency: int = 2
    write_latency: int = 2


def _memory_image() -> dict[int, int]:
    return {
        0x10: 1000,
        0x20: 2000,
        0x30: 3000,
        0x40: 4000,
        0x50: 5000,
    }


def default_scenarios() -> dict[str, Scenario]:
    scenarios = {
        "all_paths": Scenario(
            name="all_paths",
            description=(
                "Covers cold miss allocate, hit read, hit write (dirty), "
                "dirty miss with write-back, and clean miss allocate."
            ),
            requests=[
                CPURequest(1, RequestType.READ, 0x10),
                CPURequest(2, RequestType.READ, 0x10),
                CPURequest(3, RequestType.WRITE, 0x10, write_data=1111),
                CPURequest(4, RequestType.READ, 0x20),
                CPURequest(5, RequestType.READ, 0x10),
                CPURequest(6, RequestType.WRITE, 0x30, write_data=3333),
                CPURequest(7, RequestType.READ, 0x30),
            ],
            initial_memory=_memory_image(),
            read_latency=2,
            write_latency=2,
        ),
        "clean_miss_focus": Scenario(
            name="clean_miss_focus",
            description="Shows cache miss when old block is clean and direct allocate path.",
            requests=[
                CPURequest(1, RequestType.READ, 0x10),
                CPURequest(2, RequestType.READ, 0x20),
                CPURequest(3, RequestType.READ, 0x20),
            ],
            initial_memory=_memory_image(),
            read_latency=3,
            write_latency=2,
        ),
        "dirty_miss_focus": Scenario(
            name="dirty_miss_focus",
            description="Forces dirty eviction: write hit makes line dirty, next miss triggers write-back.",
            requests=[
                CPURequest(1, RequestType.READ, 0x10),
                CPURequest(2, RequestType.WRITE, 0x10, write_data=4242),
                CPURequest(3, RequestType.READ, 0x20),
                CPURequest(4, RequestType.READ, 0x10),
            ],
            initial_memory=_memory_image(),
            read_latency=2,
            write_latency=3,
        ),
        "hit_focus": Scenario(
            name="hit_focus",
            description="Demonstrates repeated hits after one initial miss.",
            requests=[
                CPURequest(1, RequestType.READ, 0x50),
                CPURequest(2, RequestType.READ, 0x50),
                CPURequest(3, RequestType.WRITE, 0x50, write_data=5050),
                CPURequest(4, RequestType.READ, 0x50),
            ],
            initial_memory=_memory_image(),
            read_latency=2,
            write_latency=2,
        ),
    }
    return scenarios
