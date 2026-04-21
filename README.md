# SystemLink Python Test Example

An end-to-end example showing how to create a fully integrated Python test application for [NI SystemLink](https://www.ni.com/systemlink). This project demonstrates the complete lifecycle — from receiving a work order, executing parametric measurements, reporting structured results, to packaging and deploying the test to managed systems.

The example test targets an **18650 Li-ion battery cell** (part number `B0CG1KL3RC`) and performs eight parametric measurement steps using simulated instruments.

## What This Example Covers

- Receiving and processing **work items** (test orders) from SystemLink
- Resolving **product specifications** (test limits) from SystemLink Test Monitor
- Executing parametric test steps with **inputs, outputs, measurements, and limits**
- Reporting structured **test results and steps** to Test Monitor
- Uploading **test log files** to SystemLink File Service
- Managing **work item state transitions** throughout the test lifecycle
- **Packaging** the test as a `.nipkg` for deployment via NI Package Manager
- **Deploying** to managed test systems using Salt states and SystemLink Jobs
- Running in both **interactive** (operator-driven) and **automated** (SystemLink-dispatched) modes

## Project Structure

```
tests/B0CG1KL3RC/
├── main.py              # CLI entry point — parses args, orchestrates init → execution
├── config.py            # Configuration & credential management (CLI → env → system)
├── initialization.py    # Work item resolution, product/DUT/system lookups
├── execution.py         # Test execution, result creation, step logging, file upload
├── simulator.py         # Simulated battery measurements (swap with real drivers)
├── requirements.txt     # Python dependencies
├── build_nipkg.bat      # Builds a versioned .nipkg file package
├── package/
│   ├── control          # nipkg metadata (name, version, architecture)
│   ├── instructions     # nipkg install/uninstall script mappings
│   ├── postinstall.bat  # Creates Python venv and installs dependencies
│   └── preuninstall.bat # Cleans up venv on uninstall
└── deploy/
    ├── install.sls              # Salt state for remote system provisioning
    ├── workflow.json            # Work item workflow definition
    ├── work-item-template.json  # Template for creating test work items
    ├── run_systemlink_job.py    # Submit and monitor Salt jobs via Jobs API
    └── ...                      # Additional deployment/debugging utilities
```

## Test Steps

| # | Measurement | Nominal | Range | Unit |
|---|-------------|---------|-------|------|
| 1 | Open Circuit Voltage | 3.7 | 2.5 – 4.2 | V |
| 2 | Voltage Under Load | — | — | V |
| 3 | Internal Resistance | — | 10 – 80 | mΩ |
| 4 | Cell Capacity | 2,500 | 2,250 – 2,750 | mAh |
| 5 | End-of-Charge Voltage | ~4.18 | ≤ 4.2 | V |
| 6 | Discharge Cutoff Voltage | ~2.55 | ≥ 2.5 | V |
| 7 | Cell Weight | 46 | 40 – 50 | g |
| 8 | Temperature Under Discharge | — | –20 – +60 | °C |

## SystemLink APIs Used

All communication uses the [`nisystemlink-clients`](https://pypi.org/project/nisystemlink-clients/) Python SDK:

| Client | Purpose |
|--------|---------|
| `WorkItemClient` | Retrieve work items, transition states (IN_PROGRESS → PENDING_APPROVAL) |
| `ProductClient` | Query/create products with test spec limits |
| `AssetManagementClient` | Resolve DUT serial numbers and fixture calibration |
| `TestMonitorClient` | Create test results and steps with measurements and limits |
| `FileClient` | Upload test log files linked to results |

## Prerequisites

- Python 3.10+
- Access to an NI SystemLink server
- `nisystemlink-clients` (see `requirements.txt`)
- If you are editing this test or creating a new test, install [`slcli`](https://github.com/ni-kismet/systemlink-cli) so you can manage the related SystemLink resources from your development machine

## Running the Test

### Interactive Mode (Development)

```bash
cd tests/B0CG1KL3RC
pip install -r requirements.txt

# Prompts for work item ID and displays a summary before executing
python main.py
```

### Automated Mode (SystemLink-Dispatched or CI)

```bash
# Provide credentials explicitly for non-managed machines
python main.py --work-item-id <ID> --server https://myserver.com --api-key <KEY>
```

On a SystemLink-managed system, credentials are discovered automatically — no `--server` or `--api-key` flags needed.

### Credential Priority

1. CLI arguments (`--server`, `--api-key`)
2. Environment variables
3. System credentials (auto-discovered on managed systems)

## Building the Package

On Windows, run:

```batch
build_nipkg.bat
```

This produces a versioned `.nipkg` in the `dist/` directory (e.g., `18650-battery-test_1.0.0.20260420083348_windows_all.nipkg`). The package installs to `C:\Program Files\NI\18650-battery-test\`.

## Deploying to a Test System

The Salt state in `deploy/install.sls` automates the full provisioning:

1. Downloads and installs Python 3.12
2. Registers the NI package feed
3. Installs the `.nipkg` via NI Package Manager
4. Creates a Python virtual environment and installs dependencies

Deploy remotely via SystemLink Jobs API using `deploy/run_systemlink_job.py`.

## Work Item Integration

The `deploy/work-item-template.json` defines a test plan template that operators use to create work orders. When a work item is moved to **START**, SystemLink dispatches a Salt job to the assigned test system that runs the test automatically.

Workflow states: `NEW → DEFINED → REVIEWED → SCHEDULED → IN_PROGRESS → PENDING_APPROVAL → COMPLETED`

## Adapting This Example

To create or edit a test, install [`slcli`](https://github.com/ni-kismet/systemlink-cli) first.

Then:

1. **Replace `simulator.py`** with real instrument drivers (PyDAQmx, NI-VISA, etc.)
2. **Update `config.py`** with your product's part number and default specifications
3. **Modify test steps** in `execution.py` to match your measurements
4. **Update package metadata** in `package/control` (name, description, maintainer)
5. **Create a new work item template** for your test workflow

## License

[MIT](LICENSE)
