# Cache Controller FSM Simulator

A comprehensive cache controller finite state machine (FSM) simulator with both CLI and GUI interfaces. This project simulates CPU-cache-memory interactions and generates detailed execution traces.

## Prerequisites

- **Python 3.9 or higher**
- Virtual environment tool (built-in `venv` or `virtualenv`)

## Setup and Installation

### 1. Create a Virtual Environment

#### On Linux/macOS:
```bash
python3 -m venv venv
source venv/bin/activate
```

#### On Windows (PowerShell):
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

#### On Windows (Command Prompt):
```cmd
python -m venv venv
venv\Scripts\activate.bat
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

## Running the Project

### GUI Mode (Default)

Launch the interactive FSM visualizer:

#### Linux/macOS:
```bash
python3 main.py
```

#### Windows:
```cmd
python main.py
```

Or explicitly specify the `gui` command:
```bash
python main.py gui
```

### CLI Mode - Run Scenarios

Execute simulation scenarios and export trace files:

#### Run a specific scenario:
```bash
python main.py run --scenario all_paths
```

#### Run all predefined scenarios:
```bash
python main.py run --scenario all
```

#### Customize output options:
```bash
python main.py run --scenario all_paths --output-dir outputs --max-rows 50
```

**Options:**
- `--scenario` - Scenario name or `all` to run every predefined scenario (default: `all_paths`)
- `--output-dir` - Directory to write CSV/Markdown trace files (default: `outputs`)
- `--max-rows` - Maximum number of trace rows in markdown tables (default: `40`)

## Scenarios

The simulator includes four predefined scenarios:

- `all_paths` - Covers the full cache controller flow, including cold miss allocate, hit read, hit write on a dirty line, dirty miss with write-back, and clean miss allocate.
- `clean_miss_focus` - Shows a cache miss on a clean line, so the controller can evict and allocate the new block directly without write-back.
- `dirty_miss_focus` - Shows a dirty eviction path, where a modified cache line must be written back to memory before the new block is loaded.
- `hit_focus` - Shows repeated cache hits after one initial miss, including both read hits and write hits on the same address.

## Output

When running scenarios, the simulator generates:
- **CSV files** - Complete trace data in CSV format
- **Markdown files** - Formatted trace tables for easy viewing

Output files are saved in the `outputs/` directory by default.

## Project Structure

```
cache-controller-fsm/
├── main.py                 # Entry point with CLI/GUI launcher
├── requirements.txt        # Python dependencies
├── cache_fsm/
│   ├── __init__.py        # Package initialization
│   ├── components.py      # Core FSM and simulator components
│   ├── models.py          # Data models and state definitions
│   ├── scenarios.py       # Predefined test scenarios
│   ├── reporting.py       # CSV and markdown output formatting
│   └── visualizer.py      # PyQt6 GUI visualizer
└── outputs/               # Generated trace files
```

## Requirements

See [requirements.txt](requirements.txt) for all Python dependencies.

## License

[No License]
