---
name: systemlink-test
description: >-
  Create Python-based device test applications that integrate with NI SystemLink.
  Use when the user asks to create a new test, build a test script, integrate a Python
  test with SystemLink, create a functional or parametric test, report test results
  to Test Monitor, handle work items in a test context, package a test as a nipkg,
  or deploy a test application to a SystemLink-managed system. Covers the full lifecycle:
  work item integration, product/spec resolution, test execution with step logging,
  result and file upload, asset/DUT tracking, nipkg packaging, and CI/CD deployment.
---

# SystemLink Python Test Application

Create Python-based functional/parametric device test applications that integrate
with NI SystemLink across the full test lifecycle.

## When to Use

- Creating a new Python test application for an electronic or mechanical device
- Integrating an existing test script with SystemLink (results, work items, assets)
- Setting up test result reporting with steps, measurements, limits, and inputs/outputs
- Packaging a test application as a `.nipkg` for feed deployment
- Creating work item templates for test scheduling

## Prerequisites

- Python 3.10+
- `nisystemlink-clients` package (sole communication layer — no direct HTTP calls)
- SystemLink server with Test Monitor, Asset Management, Work Order, and File services
- Valid API key with appropriate permissions

## Procedure

Follow these phases in order when creating a new test application.

### Phase 1: Project Setup

1. Create the project directory structure:
   ```
   tests/<PART_NUMBER>/
   ├── config.py              # Configuration, credentials, product specs
   ├── initialization.py      # Work item → product/DUT/system resolution
   ├── execution.py           # Result creation, step execution, file upload
   ├── simulator.py           # (Optional) simulated measurements for dev/test
   ├── main.py                # CLI entry point
   ├── requirements.txt       # nisystemlink-clients + hardware drivers
   ├── build_nipkg.bat        # Windows nipkg build script
   ├── package/
   │   ├── control            # nipkg metadata (name, version, deps)
   │   ├── instructions        # maps install/uninstall scripts
   │   ├── postinstall.bat    # creates venv + pip installs
   │   └── preuninstall.bat   # removes venv on uninstall
   └── deploy/
       ├── work-item-template.json
       └── workflow.json
   ```
2. Create `requirements.txt` with `nisystemlink-clients` and any hardware driver packages
3. Create a configuration module (see Phase 1a below)
4. **Never hard-code API keys** — use CLI args, environment variables, or system credentials

### Phase 1a: Configuration Module (`config.py`)

The configuration module handles three credential modes:

```python
from nisystemlink.clients.core import HttpConfiguration

def get_configuration(
    server: str | None = None,
    api_key: str | None = None,
) -> HttpConfiguration | None:
    """Build HttpConfiguration.

    Priority:
      1. Explicit server/api_key args (CLI flags for dev use).
      2. SYSTEMLINK_SERVER_URI / SYSTEMLINK_API_KEY env vars.
      3. None — SDK auto-discovers credentials on a managed system.
    """
    server = server or os.environ.get("SYSTEMLINK_SERVER_URI")
    api_key = api_key or os.environ.get("SYSTEMLINK_API_KEY")

    if server and api_key:
        return HttpConfiguration(server_uri=server, api_key=api_key)
    return None
```

**IMPORTANT**: When `get_configuration()` returns `None`, the SDK's `HttpConfigurationManager`
auto-discovers credentials on a managed system. This is the production path. The explicit
server/api_key path is for **developer machines** that are not SystemLink-managed.

Also define `PRODUCT_SPECS` as a dict of default spec properties. These serve as fallbacks
when the product on the server doesn't have all `spec.*` properties populated:

```python
PRODUCT_SPECS = {
    "spec.voltage_low_limit": "2.5",
    "spec.voltage_high_limit": "4.2",
    # ... all spec properties with string values
}
```

### Phase 1b: CLI Entry Point (`main.py`)

The main module MUST support three execution modes via argparse:

```python
parser.add_argument("--work-item-id", help="Work item ID. Omit for interactive.")
parser.add_argument("--server", help="SystemLink server URI. For dev use.")
parser.add_argument("--api-key", help="SystemLink API key. For dev use.")
```

- **Interactive mode**: no `--work-item-id` → prompts operator
- **Automated mode**: `--work-item-id` passed → no prompts, headless
- **Developer mode**: `--server` + `--api-key` → uses explicit credentials on non-managed machine

### Phase 2: Initialization Module (`initialization.py`)

Build the initialization logic that runs before any test steps execute.

1. **Accept work item ID** — via CLI argument or interactive prompt
2. **Query the work item** — `WorkItemClient(configuration).get_work_item(work_item_id)`
3. **Resolve the product** — query by part number; if missing, create with `PRODUCT_SPECS` defaults (interactive only)
4. **Resolve spec properties** — read product `properties` for limits. Fall back to `PRODUCT_SPECS` for any missing `spec.*` key
5. **Resolve the DUT** — query Asset API using `work_item.resources.duts.selections[0].id`
6. **Resolve the system/minionId** — see Phase 2a
7. **Check fixture calibration** — warn if `PAST_RECOMMENDED_DUE_DATE`
8. **Read work item properties** — available as test parameters
9. **Validate** — abort if required parameters missing
10. **Display summary** — in interactive mode, show parameters for operator confirmation

### Phase 2a: System ID / MinionId Resolution

The `system_id` is critical — it links results and files to the correct test system.

**Two modes:**

- **Managed system** (production, `configuration is None`): Read the local minionId from disk:
  - Windows: `C:\ProgramData\National Instruments\salt\conf\minion_id`
  - Linux: `/etc/salt/minion_id`
  - The file contains a plain-text minion ID string

- **Developer system** (`configuration is not None`): Use the system resource assigned to the
  work item: `work_item.resources.systems.selections[0].id`

```python
def _resolve_system_id(work_item: WorkItem, is_dev_mode: bool) -> str | None:
    if not is_dev_mode:
        minion_id = _read_local_minion_id()
        if minion_id:
            return minion_id
    # Dev mode or local read failed: use work item system resource
    if work_item.resources and work_item.resources.systems:
        selections = work_item.resources.systems.selections or []
        if selections and selections[0].id:
            return selections[0].id
    return None
```

### Phase 3: Test Execution (`execution.py`)

Build the test runner that creates results and steps.

1. **Create a test result** with status `RUNNING` before any steps execute. Include:
   - `program_name`, `serial_number`, `part_number`, `operator`, `host_name`, `started_at`
   - `system_id` (the resolved minionId)
   - Property `workItemId` set to the originating work item ID
   - `workspace` from the work item
2. **Transition work item** to `IN_PROGRESS`
3. **Execute steps sequentially** — see Phase 3a
4. **Upload files** — see Phase 3b
5. **Update the result** — set final status, `total_time_in_seconds`, `file_ids`
6. **Transition work item** to `CLOSED`

### Phase 3a: Step Creation

**CRITICAL SDK requirements for `CreateStepRequest`:**

- `step_id` is **required** — generate with `str(uuid.uuid4())`
- `result_id` is **required**
- `name` is **required**
- Use `NamedValue` objects for `inputs` and `outputs` lists
- Use `StepData` with `Measurement` objects for parametric data
- Use `Status(status_type=StatusType.PASSED)` for status

```python
import uuid

def _build_step(result_id, name, step_type, measurement_value, low_limit, high_limit, units, ...):
    status_type = _compare(measurement_value, low_limit, high_limit)
    return CreateStepRequest(
        step_id=str(uuid.uuid4()),   # REQUIRED — must be unique
        result_id=result_id,          # REQUIRED
        name=name,                    # REQUIRED
        step_type=step_type,
        status=Status(status_type=status_type),
        inputs=[NamedValue(name="input.load_current", value="2.5 A")],
        outputs=[NamedValue(name="output.voltage", value=str(value))],
        data=StepData(
            text=name,
            parameters=[
                Measurement(
                    name=name,
                    status=status_type.value,
                    measurement=str(measurement_value),
                    lowLimit=str(low_limit),
                    highLimit=str(high_limit),
                    units=units,
                    comparisonType="GELE",
                )
            ],
        ),
        properties={
            "step.startedAt": started_at.isoformat(),
            "step.duration": str(round(duration, 3)),
            "step.limitSource": f"product:{part_number}",
        },
    )
```

**Spec lookup with fallback:**

```python
def _get_spec(product_props: dict, key: str) -> float:
    value = product_props.get(key) or PRODUCT_SPECS.get(key)
    if value is None:
        raise RuntimeError(f"Missing product spec: {key}")
    return float(value)
```

### Phase 3b: File Upload

**CRITICAL SDK requirements for `FileClient.upload_file()`:**

- The `file` parameter takes a **`BinaryIO`** object (not a file path)
- Returns a **`str`** (the file ID), not an object with `.id`
- The `metadata` parameter is a `dict[str, str]` — the SDK calls `json.dumps()` internally

```python
with open(log_path, "rb") as fp:
    file_id = file_client.upload_file(
        file=fp,
        metadata={
            "resultId": result_id,
            "workItemId": ctx.work_item_id,
            "minionId": ctx.system_id or "",
            "fileType": "test-log",
        },
        workspace=ctx.work_item.workspace,
    )
```

### Phase 4: Result and Step Schema

**Required result fields (CreateResultRequest):**

| Field | Required | Notes |
|---|---|---|
| `status` | Yes | `Status(status_type=StatusType.RUNNING)` |
| `program_name` | Yes | String |
| `started_at` | No | `datetime` with UTC timezone |
| `system_id` | No | MinionId string |
| `host_name` | No | `socket.gethostname()` |
| `part_number` | No | From work item |
| `serial_number` | No | From DUT asset |
| `operator` | No | From work item `assigned_to` |
| `properties` | No | Dict — include `workItemId` |
| `keywords` | No | List of strings |
| `workspace` | No | From work item |

**Required step fields (CreateStepRequest):**

| Field | Required | Notes |
|---|---|---|
| `step_id` | **Yes** | `str(uuid.uuid4())` — MUST be provided |
| `result_id` | **Yes** | From created result |
| `name` | **Yes** | Step display name |
| `status` | No | `Status(status_type=...)` |
| `step_type` | No | `NumericLimit`, `StringValue`, `PassFail` |
| `inputs` | No | `List[NamedValue]` |
| `outputs` | No | `List[NamedValue]` |
| `data` | No | `StepData` with `Measurement` list |
| `properties` | No | Dict for `step.*` and `input.*`/`output.*` |

**UpdateResultRequest** — only `id` is required. Set `status`, `total_time_in_seconds`, `file_ids`, `properties`.

### Phase 5: SDK Client Usage

All SystemLink communication MUST use `nisystemlink-clients`. No direct HTTP.

**Verified import paths:**

```python
from nisystemlink.clients.core import HttpConfiguration
from nisystemlink.clients.testmonitor import TestMonitorClient
from nisystemlink.clients.testmonitor.models import (
    CreateResultRequest, CreateStepRequest, UpdateResultRequest,
    Measurement, NamedValue, Status, StatusType, StepData,
)
from nisystemlink.clients.product import ProductClient
from nisystemlink.clients.product.models import CreateProductRequest, QueryProductsRequest
from nisystemlink.clients.work_item import WorkItemClient
from nisystemlink.clients.work_item.models import (
    WorkItem, UpdateWorkItemRequest, UpdateWorkItemsRequest,
)
from nisystemlink.clients.assetmanagement import AssetManagementClient
from nisystemlink.clients.assetmanagement.models import (
    Asset, AssetType, CalibrationStatus, QueryAssetsRequest,
)
from nisystemlink.clients.file import FileClient
```

**SDK gotchas:**

| Pitfall | Correct Usage |
|---|---|
| `CreateStepRequest` missing `step_id` | Always set `step_id=str(uuid.uuid4())` |
| `FileClient.upload_file(file=path)` | Pass `BinaryIO`, not `Path`: `open(path, "rb")` |
| `upload_file()` returns object with `.id` | Returns `str` directly |
| `get_configuration()` returns `None` on managed system | SDK auto-discovers — do not raise error |
| `StatusType` enum values | Use `StatusType.PASSED`, not string `"PASSED"` |
| `Measurement` fields are strings | `measurement=str(value)`, `lowLimit=str(limit)` |
| Product properties may be incomplete | Fall back to `PRODUCT_SPECS` defaults |
| Work item state transitions | Use string values: `"IN_PROGRESS"`, `"CLOSED"` |

### Phase 6: Packaging and Deployment

Package as a `.nipkg` for distribution through SystemLink feeds.

#### 6a: Package directory structure

```
tests/<PART_NUMBER>/
├── package/
│   ├── control          # nipkg metadata
│   ├── instructions     # maps install/uninstall scripts
│   ├── postinstall.bat  # creates venv + pip installs
│   └── preuninstall.bat # removes venv on uninstall
├── build_nipkg.bat      # build script (run on Windows)
└── ...source files...
```

#### 6b: Control file (`package/control`)

```
Package: <package-name>
Version: 1.0.0
Section: test-applications
Architecture: windows_all
Depends: ni-python (>= 3.10)
Maintainer: Team Name <email>
XB-Plugin: file
XB-UserVisible: yes
Description: Short description
 Extended description (indented with one space).
```

#### 6c: Instructions file (`package/instructions`)

```ini
[Instructions]
postinstall=postinstall.bat
preuninstall=preuninstall.bat
```

#### 6d: Post-install script (`package/postinstall.bat`)

Creates a Python venv at the install location and installs dependencies:

```bat
@echo off
set INSTALL_DIR=C:\Program Files\NI\<package-name>
set VENV_DIR=%INSTALL_DIR%\venv
python -m venv "%VENV_DIR%"
"%VENV_DIR%\Scripts\pip.exe" install --no-cache-dir -r "%INSTALL_DIR%\requirements.txt"
```

#### 6e: Pre-uninstall script (`package/preuninstall.bat`)

```bat
@echo off
set INSTALL_DIR=C:\Program Files\NI\<package-name>
if exist "%INSTALL_DIR%\venv" rmdir /s /q "%INSTALL_DIR%\venv"
```

#### 6f: Build script (`build_nipkg.bat`)

The build script:
1. Creates `build/nipkg/data/Program Files/NI/<package-name>/` with app source files
2. Creates `build/nipkg/control/` with control, instructions, and install scripts
3. Runs `nipkg pack build/nipkg dist/<package-name>_<version>_windows_all.nipkg`

**Requires**: NI Package Manager CLI (`nipkg`) on the build machine (Windows).

#### 6g: Upload and deploy

```bash
# Upload to a SystemLink feed
slcli feed package upload --feed "<feed-name>" --file dist/<package>.nipkg

# On the target system, the package installs to:
# C:\Program Files\NI\<package-name>\
# Run via:
"C:\Program Files\NI\<package-name>\venv\Scripts\python.exe" ^
  "C:\Program Files\NI\<package-name>\main.py" --work-item-id <ID>
```

### Phase 7: Work Item Template and Workflow

Create and publish a work item template with an associated workflow.

#### 7a: Workflow (`deploy/workflow.json`)

Define the state machine for work item lifecycle. Standard states:

```
NEW → DEFINED → REVIEWED → SCHEDULED → IN_PROGRESS → PENDING_APPROVAL → CLOSED
                                         ↕ PAUSED                        CANCELED
```

The workflow JSON contains:
- **`actions`**: Named actions with `executionAction` (ABORT, APPROVE, CANCEL, END, PAUSE, REJECT, RESUME, SCHEDULE, START, SUBMIT, UNSCHEDULE)
- **`states`**: Each with `substates` and `availableActions` that define valid transitions

Import with: `slcli workitem workflow import --file deploy/workflow.json -w <WORKSPACE>`
Update with: `slcli workitem workflow update --id <WORKFLOW_ID> --file deploy/workflow.json`

#### 7b: Template (`deploy/work-item-template.json`)

**IMPORTANT**: Use `partNumbers` (array of strings), NOT `partNumberFilter`.
Include `workflowId` to associate the workflow.

```json
{
  "name": "My Test Name",
  "type": "testplan",
  "templateGroup": "My Test Group",
  "partNumbers": ["PART-NUMBER-HERE"],
  "workflowId": "<WORKFLOW_ID>",
  "description": "...",
  "summary": "...",
  "resources": {
    "systems": { "count": 1, "filter": "" },
    "duts": { "count": 1, "filter": "AssetType == \"DEVICE_UNDER_TEST\"" },
    "fixtures": { "count": 0, "filter": "" }
  },
  "properties": {
    "param_key": "default_value"
  }
}
```

Publish: `slcli workitem template create --file deploy/work-item-template.json -w <WORKSPACE>`
Update: `slcli workitem template update <TEMPLATE_ID> --file deploy/work-item-template.json`

#### 7c: Deployment order

1. Import workflow first → get `<WORKFLOW_ID>`
2. Add `workflowId` to template JSON
3. Create/update template

### Phase 8: Error Handling

| Scenario | Behavior |
|---|---|
| Step out of limits | Record FAILED, continue remaining steps |
| Hardware timeout | Retry once, abort with ERRORED and diagnostics |
| Server unreachable | Queue result locally, retry on next cycle |
| Missing serial/part number | Abort, do not create partial result |
| API key expired | Log error, halt, alert operator |

Retry transient HTTP errors (429, 500, 502, 503) with exponential backoff, up to 3 attempts.

## Key Rules

1. **`nisystemlink-clients` only** — no direct HTTP calls to SystemLink APIs
2. **No hard-coded credentials** — use CLI args, environment variables, or system credentials
3. **`step_id` on every step** — `CreateStepRequest` requires `step_id=str(uuid.uuid4())`
4. **`workItemId` on every result** — links results to originating work order
5. **Limits from product specs with fallback** — read from product properties, fall back to `PRODUCT_SPECS` defaults
6. **File upload uses `BinaryIO`** — `open(path, "rb")`, not `Path`; returns `str` file ID
7. **MinionId from local file on managed systems** — Windows: `C:\ProgramData\National Instruments\salt\conf\minion_id`, Linux: `/etc/salt/minion_id`; dev mode uses work item system resource
8. **Work item template uses `partNumbers` array** — not `partNumberFilter` string
9. **Continue after step failure** — do not abort on first failed step
10. **Three execution modes** — interactive (prompt), automated (headless), developer (explicit creds)

## References

- [Full requirements document](./references/requirements.md)
- [Project structure](./references/project-structure.md)
