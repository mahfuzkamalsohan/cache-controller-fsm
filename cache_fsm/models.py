from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RequestType(Enum):
    READ = "READ"
    WRITE = "WRITE"


class MemoryOpType(Enum):
    READ = "READ"
    WRITE = "WRITE"


class ControllerState(Enum):
    IDLE = "Idle"
    COMPARE_TAG = "Compare Tag"
    ALLOCATE = "Allocate"
    WRITE_BACK = "Write-Back"


@dataclass(frozen=True)
class CPURequest:
    req_id: int
    req_type: RequestType
    address: int
    write_data: Optional[int] = None


@dataclass
class CPUResponse:
    req_id: int
    req_type: RequestType
    address: int
    hit: bool
    data: Optional[int] = None
    wait_cycles: int = 0


@dataclass
class CacheLine:
    valid: bool = False
    dirty: bool = False
    tag: Optional[int] = None
    data: int = 0


@dataclass
class MemoryResult:
    op: MemoryOpType
    block_addr: int
    data: Optional[int] = None


@dataclass
class SignalSnapshot:
    cpu_req_valid: bool = False
    cpu_req_type: str = "-"
    cpu_req_addr: Optional[int] = None
    cpu_waiting: bool = False
    cache_ready: bool = False
    cache_hit: bool = False
    mem_read: bool = False
    mem_write: bool = False
    mem_ready: bool = False
    mem_busy: bool = False
    mem_addr: Optional[int] = None


@dataclass
class StepResult:
    state_before: ControllerState
    state_after: ControllerState
    transition_key: str
    transition_label: str
    signals: SignalSnapshot
    issued_request: Optional[CPURequest] = None
    active_request: Optional[CPURequest] = None
    completed_response: Optional[CPUResponse] = None


@dataclass
class CycleTrace:
    cycle: int
    state_before: ControllerState
    state_after: ControllerState
    transition_key: str
    transition_label: str
    signals: SignalSnapshot
    line_valid: bool
    line_dirty: bool
    line_tag: Optional[int]
    line_data: int
    queue_depth: int
    issued_request: Optional[CPURequest] = None
    active_request: Optional[CPURequest] = None
    completed_response: Optional[CPUResponse] = None


@dataclass
class SimulationSummary:
    cycles: int
    responses: list[CPUResponse] = field(default_factory=list)
