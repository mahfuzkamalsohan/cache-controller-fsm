from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from .models import (
    CPURequest,
    CPUResponse,
    CacheLine,
    ControllerState,
    CycleTrace,
    MemoryOpType,
    MemoryResult,
    RequestType,
    SignalSnapshot,
    SimulationSummary,
    StepResult,
)


@dataclass
class PendingMemoryOp:
    op: MemoryOpType
    block_addr: int
    data: Optional[int]
    remaining_cycles: int


class SimpleCPU:
    """A simple in-order CPU that issues one request at a time."""

    def __init__(self, requests: list[CPURequest]) -> None:
        self._queue: Deque[CPURequest] = deque(requests)
        self.current_request: Optional[CPURequest] = None
        self._issue_cycle: Optional[int] = None
        self.responses: list[CPUResponse] = []

    def maybe_issue(self, can_issue: bool, cycle: int) -> Optional[CPURequest]:
        if not can_issue:
            return None
        if self.current_request is not None:
            return None
        if not self._queue:
            return None
        self.current_request = self._queue.popleft()
        self._issue_cycle = cycle
        return self.current_request

    def complete(self, response: CPUResponse, cycle: int) -> None:
        if self.current_request is None:
            raise RuntimeError("CPU got a response with no active request")
        if self._issue_cycle is None:
            raise RuntimeError("CPU issue cycle is unknown")
        response.wait_cycles = cycle - self._issue_cycle + 1
        self.responses.append(response)
        self.current_request = None
        self._issue_cycle = None

    @property
    def queue_depth(self) -> int:
        return len(self._queue)

    @property
    def is_done(self) -> bool:
        return self.current_request is None and not self._queue


class SimpleMemory:
    """A memory model that never misses, but takes fixed read/write latency."""

    def __init__(
        self,
        initial_storage: Optional[dict[int, int]] = None,
        read_latency: int = 2,
        write_latency: int = 2,
    ) -> None:
        if read_latency < 1 or write_latency < 1:
            raise ValueError("Memory latencies must be >= 1 cycle")
        self.storage: dict[int, int] = dict(initial_storage or {})
        self.read_latency = read_latency
        self.write_latency = write_latency
        self.pending_op: Optional[PendingMemoryOp] = None

    def start_read(self, block_addr: int) -> None:
        if self.pending_op is not None:
            raise RuntimeError("Memory is busy")
        self.pending_op = PendingMemoryOp(
            op=MemoryOpType.READ,
            block_addr=block_addr,
            data=None,
            remaining_cycles=self.read_latency,
        )

    def start_write(self, block_addr: int, data: int) -> None:
        if self.pending_op is not None:
            raise RuntimeError("Memory is busy")
        self.pending_op = PendingMemoryOp(
            op=MemoryOpType.WRITE,
            block_addr=block_addr,
            data=data,
            remaining_cycles=self.write_latency,
        )

    def tick(self) -> tuple[bool, Optional[MemoryResult]]:
        if self.pending_op is None:
            return False, None

        self.pending_op.remaining_cycles -= 1
        if self.pending_op.remaining_cycles > 0:
            return False, None

        op = self.pending_op
        self.pending_op = None

        if op.op is MemoryOpType.WRITE:
            if op.data is None:
                raise RuntimeError("Write operation has no data")
            self.storage[op.block_addr] = op.data
            return True, MemoryResult(op=MemoryOpType.WRITE, block_addr=op.block_addr, data=op.data)

        # On a read, return existing data, or synthesize deterministic data.
        value = self.storage.get(op.block_addr, op.block_addr * 100)
        return True, MemoryResult(op=MemoryOpType.READ, block_addr=op.block_addr, data=value)

    @property
    def busy(self) -> bool:
        return self.pending_op is not None

    @property
    def pending_addr(self) -> Optional[int]:
        return self.pending_op.block_addr if self.pending_op else None

    @property
    def pending_type(self) -> Optional[MemoryOpType]:
        return self.pending_op.op if self.pending_op else None


class CacheControllerFSM:
    """Single-line cache controller with FSM from the classic textbook diagram."""

    TRANSITIONS: dict[str, str] = {
        "NONE": "No state change",
        "IDLE_TO_COMPARE": "Valid CPU request",
        "COMPARE_TO_IDLE_HIT": "Cache Hit / Mark Cache Ready",
        "COMPARE_TO_ALLOCATE_MISS_CLEAN": "Cache Miss and Old Block is Clean",
        "COMPARE_TO_WRITEBACK_MISS_DIRTY": "Cache Miss and Old Block is Dirty",
        "WRITEBACK_STALL": "Memory not Ready",
        "WRITEBACK_TO_ALLOCATE_READY": "Memory Ready",
        "ALLOCATE_STALL": "Memory not Ready",
        "ALLOCATE_TO_COMPARE_READY": "Memory Ready",
    }

    def __init__(self) -> None:
        self.state = ControllerState.IDLE
        self.cache_line = CacheLine()
        self.active_request: Optional[CPURequest] = None
        self.active_request_was_miss = False
        self.last_hit = False

    def can_accept_cpu_request(self) -> bool:
        return self.state is ControllerState.IDLE and self.active_request is None

    def _build_signal_base(
        self,
        cpu_request: Optional[CPURequest],
        mem_ready: bool,
        memory: SimpleMemory,
    ) -> SignalSnapshot:
        return SignalSnapshot(
            cpu_req_valid=cpu_request is not None,
            cpu_req_type=cpu_request.req_type.value if cpu_request else "-",
            cpu_req_addr=cpu_request.address if cpu_request else None,
            cache_ready=False,
            cache_hit=False,
            mem_read=False,
            mem_write=False,
            mem_ready=mem_ready,
            mem_busy=memory.busy,
            mem_addr=memory.pending_addr,
        )

    def step(
        self,
        cpu_request: Optional[CPURequest],
        mem_ready: bool,
        mem_result: Optional[MemoryResult],
        memory: SimpleMemory,
    ) -> StepResult:
        state_before = self.state
        transition_key = "NONE"
        completed: Optional[CPUResponse] = None
        signals = self._build_signal_base(cpu_request, mem_ready, memory)

        if self.state is ControllerState.IDLE:
            if cpu_request is not None:
                self.active_request = cpu_request
                self.active_request_was_miss = False
                self.state = ControllerState.COMPARE_TAG
                transition_key = "IDLE_TO_COMPARE"
            else:
                signals.cache_ready = True

        elif self.state is ControllerState.COMPARE_TAG:
            if self.active_request is None:
                raise RuntimeError("COMPARE_TAG reached without an active CPU request")

            req = self.active_request
            hit = self.cache_line.valid and self.cache_line.tag == req.address
            self.last_hit = hit

            if hit:
                signals.cache_hit = True
                signals.cache_ready = True
                transition_key = "COMPARE_TO_IDLE_HIT"

                if req.req_type is RequestType.READ:
                    completed = CPUResponse(
                        req_id=req.req_id,
                        req_type=req.req_type,
                        address=req.address,
                        hit=not self.active_request_was_miss,
                        data=self.cache_line.data,
                    )
                else:
                    if req.write_data is None:
                        raise RuntimeError("WRITE request has no write_data")
                    self.cache_line.data = req.write_data
                    self.cache_line.dirty = True
                    completed = CPUResponse(
                        req_id=req.req_id,
                        req_type=req.req_type,
                        address=req.address,
                        hit=not self.active_request_was_miss,
                        data=req.write_data,
                    )

                self.active_request = None
                self.active_request_was_miss = False
                self.state = ControllerState.IDLE

            else:
                self.active_request_was_miss = True
                if self.cache_line.valid and self.cache_line.dirty:
                    transition_key = "COMPARE_TO_WRITEBACK_MISS_DIRTY"
                    self.state = ControllerState.WRITE_BACK
                    signals.mem_write = True
                    signals.mem_addr = self.cache_line.tag
                    memory.start_write(self.cache_line.tag, self.cache_line.data)
                else:
                    transition_key = "COMPARE_TO_ALLOCATE_MISS_CLEAN"
                    self.state = ControllerState.ALLOCATE
                    signals.mem_read = True
                    signals.mem_addr = req.address
                    memory.start_read(req.address)

        elif self.state is ControllerState.WRITE_BACK:
            signals.mem_write = True
            signals.mem_addr = self.cache_line.tag
            if mem_ready:
                transition_key = "WRITEBACK_TO_ALLOCATE_READY"
                self.state = ControllerState.ALLOCATE
                if self.active_request is None:
                    raise RuntimeError("WRITE_BACK completed without active request")
                memory.start_read(self.active_request.address)
                signals.mem_read = True
                signals.mem_addr = self.active_request.address
                self.cache_line.dirty = False
            else:
                transition_key = "WRITEBACK_STALL"

        elif self.state is ControllerState.ALLOCATE:
            signals.mem_read = True
            signals.mem_addr = self.active_request.address if self.active_request else signals.mem_addr
            if mem_ready:
                if mem_result is None or mem_result.op is not MemoryOpType.READ:
                    raise RuntimeError("ALLOCATE expected a memory READ completion")
                if self.active_request is None:
                    raise RuntimeError("ALLOCATE completed without active request")

                self.cache_line.valid = True
                self.cache_line.dirty = False
                self.cache_line.tag = self.active_request.address
                self.cache_line.data = mem_result.data if mem_result.data is not None else 0

                transition_key = "ALLOCATE_TO_COMPARE_READY"
                self.state = ControllerState.COMPARE_TAG
            else:
                transition_key = "ALLOCATE_STALL"

        state_after = self.state
        return StepResult(
            state_before=state_before,
            state_after=state_after,
            transition_key=transition_key,
            transition_label=self.TRANSITIONS[transition_key],
            signals=signals,
            issued_request=cpu_request,
            active_request=self.active_request,
            completed_response=completed,
        )


class CacheSystemSimulator:
    def __init__(self, cpu: SimpleCPU, memory: SimpleMemory, controller: CacheControllerFSM) -> None:
        self.cpu = cpu
        self.memory = memory
        self.controller = controller
        self.cycle = 0
        self.trace: list[CycleTrace] = []

    def step(self) -> CycleTrace:
        self.cycle += 1

        mem_ready, mem_result = self.memory.tick()
        issued = self.cpu.maybe_issue(
            can_issue=self.controller.can_accept_cpu_request(),
            cycle=self.cycle,
        )

        step_result = self.controller.step(
            cpu_request=issued,
            mem_ready=mem_ready,
            mem_result=mem_result,
            memory=self.memory,
        )

        if step_result.completed_response is not None:
            self.cpu.complete(step_result.completed_response, cycle=self.cycle)

        step_result.signals.cpu_waiting = self.cpu.current_request is not None

        trace = CycleTrace(
            cycle=self.cycle,
            state_before=step_result.state_before,
            state_after=step_result.state_after,
            transition_key=step_result.transition_key,
            transition_label=step_result.transition_label,
            signals=step_result.signals,
            line_valid=self.controller.cache_line.valid,
            line_dirty=self.controller.cache_line.dirty,
            line_tag=self.controller.cache_line.tag,
            line_data=self.controller.cache_line.data,
            queue_depth=self.cpu.queue_depth,
            issued_request=step_result.issued_request,
            active_request=self.controller.active_request,
            completed_response=step_result.completed_response,
        )
        self.trace.append(trace)
        return trace

    def is_done(self) -> bool:
        return (
            self.cpu.is_done
            and self.controller.state is ControllerState.IDLE
            and self.controller.active_request is None
            and not self.memory.busy
        )

    def run(self, max_cycles: int = 200) -> SimulationSummary:
        while not self.is_done():
            if self.cycle >= max_cycles:
                raise TimeoutError("Simulation exceeded max_cycles")
            self.step()
        return SimulationSummary(cycles=self.cycle, responses=list(self.cpu.responses))
