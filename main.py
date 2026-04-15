from __future__ import annotations

import argparse
from pathlib import Path

from cache_fsm.components import CacheControllerFSM, CacheSystemSimulator, SimpleCPU, SimpleMemory
from cache_fsm.reporting import markdown_table, write_trace_csv
from cache_fsm.scenarios import Scenario, default_scenarios


def build_simulator(scenario: Scenario) -> CacheSystemSimulator:
    cpu = SimpleCPU(list(scenario.requests))
    memory = SimpleMemory(
        initial_storage=dict(scenario.initial_memory),
        read_latency=scenario.read_latency,
        write_latency=scenario.write_latency,
    )
    controller = CacheControllerFSM()
    return CacheSystemSimulator(cpu=cpu, memory=memory, controller=controller)


def run_single_scenario(name: str, scenario: Scenario, output_dir: Path, max_rows: int) -> None:
    sim = build_simulator(scenario)
    summary = sim.run(max_cycles=500)

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{name}_trace.csv"
    table_path = output_dir / f"{name}_trace.md"
    write_trace_csv(csv_path, sim.trace)
    table_path.write_text(markdown_table(sim.trace, max_rows=max_rows), encoding="utf-8")

    print(f"Scenario: {name}")
    print(f"Description: {scenario.description}")
    print(f"Total cycles: {summary.cycles}")
    print(f"Trace CSV: {csv_path}")
    print(f"Trace Markdown: {table_path}")
    print("Responses:")
    for response in summary.responses:
        print(
            "  "
            f"#{response.req_id} {response.req_type.value} "
            f"0x{response.address:X} hit={response.hit} "
            f"data={response.data} wait={response.wait_cycles}"
        )
    print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cache controller FSM simulator")
    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run", help="Run one or more scenarios and export traces")
    run_parser.add_argument(
        "--scenario",
        default="all_paths",
        help="Scenario key or 'all' to run every predefined scenario",
    )
    run_parser.add_argument(
        "--output-dir",
        default="outputs",
        help="Directory to write CSV/Markdown trace files",
    )
    run_parser.add_argument(
        "--max-rows",
        type=int,
        default=40,
        help="Maximum number of trace rows to include in markdown tables",
    )

    sub.add_parser("gui", help="Launch PyQt6 FSM visualizer")

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.command in (None, "gui"):
        from cache_fsm.visualizer import FSMVisualizerApp

        app = FSMVisualizerApp()
        app.run()
        return

    scenarios = default_scenarios()
    output_dir = Path(args.output_dir)

    if args.scenario == "all":
        for name, scenario in scenarios.items():
            run_single_scenario(name, scenario, output_dir, max_rows=args.max_rows)
        return

    if args.scenario not in scenarios:
        available = ", ".join(sorted(scenarios.keys()))
        raise SystemExit(f"Unknown scenario '{args.scenario}'. Available: {available}, all")

    run_single_scenario(args.scenario, scenarios[args.scenario], output_dir, max_rows=args.max_rows)


if __name__ == "__main__":
    main()
