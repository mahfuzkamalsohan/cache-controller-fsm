from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from .models import CPURequest, CPUResponse, CycleTrace


def _fmt_addr(address: int | None) -> str:
    if address is None:
        return "-"
    return f"0x{address:X}"


def _fmt_request(req: CPURequest | None) -> str:
    if req is None:
        return "-"
    if req.req_type.value == "WRITE":
        return f"#{req.req_id} {req.req_type.value} {_fmt_addr(req.address)} <= {req.write_data}"
    return f"#{req.req_id} {req.req_type.value} {_fmt_addr(req.address)}"


def _fmt_response(resp: CPUResponse | None) -> str:
    if resp is None:
        return "-"
    data = "-" if resp.data is None else str(resp.data)
    return (
        f"#{resp.req_id} {resp.req_type.value} {_fmt_addr(resp.address)} "
        f"hit={resp.hit} data={data} wait={resp.wait_cycles}"
    )


def trace_rows(traces: Iterable[CycleTrace]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in traces:
        rows.append(
            {
                "cycle": str(item.cycle),
                "state_before": item.state_before.value,
                "state_after": item.state_after.value,
                "transition": item.transition_label,
                "issued_request": _fmt_request(item.issued_request),
                "active_request": _fmt_request(item.active_request),
                "completed_response": _fmt_response(item.completed_response),
                "cache_ready": str(item.signals.cache_ready),
                "cache_hit": str(item.signals.cache_hit),
                "mem_read": str(item.signals.mem_read),
                "mem_write": str(item.signals.mem_write),
                "mem_ready": str(item.signals.mem_ready),
                "mem_busy": str(item.signals.mem_busy),
                "mem_addr": _fmt_addr(item.signals.mem_addr),
                "line_valid": str(item.line_valid),
                "line_dirty": str(item.line_dirty),
                "line_tag": _fmt_addr(item.line_tag),
                "line_data": str(item.line_data),
                "queue_depth": str(item.queue_depth),
            }
        )
    return rows


def write_trace_csv(path: Path, traces: Iterable[CycleTrace]) -> None:
    rows = trace_rows(traces)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(traces: Iterable[CycleTrace], max_rows: int = 30) -> str:
    rows = trace_rows(traces)
    if not rows:
        return "No rows"

    headers = [
        "cycle",
        "state_before",
        "state_after",
        "transition",
        "issued_request",
        "completed_response",
        "cache_ready",
        "cache_hit",
        "mem_read",
        "mem_write",
        "mem_ready",
        "line_valid",
        "line_dirty",
        "line_tag",
    ]
    head = rows[:max_rows]

    out = []
    out.append("| " + " | ".join(headers) + " |")
    out.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in head:
        out.append("| " + " | ".join(row[h] for h in headers) + " |")

    if len(rows) > max_rows:
        out.append(f"\n... ({len(rows) - max_rows} more rows omitted)")
    return "\n".join(out)
