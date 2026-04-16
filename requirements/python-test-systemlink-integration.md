# Requirements: Python-Based Device Test Integration with SystemLink

**Version:** 1.0  
**Date:** April 16, 2026  
**Audience:** Test engineers writing Python-based functional/parametric tests  
**Scope:** Full workflow — work items → test execution → result upload → reporting

---

## 1. Overview

This document defines the requirements for integrating a Python-based functional or parametric device test with NI SystemLink. The integration covers the complete test lifecycle: receiving work orders, executing tests, publishing structured results (with pass/fail verdicts and measurements), and closing out work items.

---

## 2. System Prerequisites

| Requirement | Details |
|---|---|
| **SystemLink Server** | SystemLink 2024 R1 or later with Test Monitor, Asset Management, and Work Order services enabled |
| **Python** | 3.10 or later |
| **SystemLink Python Client** | `nisystemlink-clients` package (latest) — the **sole** communication layer for all SystemLink server interactions. No direct HTTP/REST calls. |
| **Authentication** | Valid API key or SystemLink system credentials (managed system). Dev mode accepts `--server` and `--api-key` CLI flags. |
| **Network** | Test system must have HTTPS access to the SystemLink server API |

---

## 3. Functional Requirements

### 3.1 Work Item Integration

| ID | Requirement | Priority |
|---|---|---|
| WI-01 | The test script SHALL query SystemLink for assigned work items filtered by system, state, and part number. | Must |
| WI-02 | The test script SHALL transition the work item to an "In Progress" state before test execution begins. | Must |
| WI-03 | The test script SHALL transition the work item to "Completed" or "Failed" after execution finishes. | Must |
| WI-04 | The test script SHOULD read test parameters (part number, serial number, operator, configuration) from the work item metadata. | Should |
| WI-05 | The test script MAY support receiving work item assignments via a SystemLink routine trigger (event-driven). | May |

### 3.2 Test Initialization and Parameter Resolution

When a new test run begins, the system SHALL collect context from the work item and its linked resources before executing any test steps.

| ID | Requirement | Priority |
|---|---|---|
| TI-01 | The test script SHALL accept a **work item ID** via a CLI argument (e.g., `--work-item-id <ID>`). It SHALL also accept optional `--server` and `--api-key` arguments for developer mode on non-managed systems. If the work item ID argument is not provided, it SHALL prompt the operator interactively (via CLI input, GUI dialog, or barcode scan). | Must |
| TI-02 | The test script SHALL query the SystemLink Work Item API using the provided work item ID and retrieve the full work item record. | Must |
| TI-03 | The test script SHALL resolve the **product** linked to the work item (via part number) by querying the Test Monitor Product API. | Must |
| TI-04 | If the product exists, the test script SHALL read the product's **properties** and use them as test specifications and conditions (e.g., voltage limits, temperature range, expected resistance). | Must |
| TI-05 | If the product does **not** exist, the test script SHALL prompt the operator for a **data sheet** (file path or URL) and/or manual specification entry, then create the product in Test Monitor with the provided specs stored as product properties. | Must |
| TI-06 | The test script SHALL resolve the **DUT** (Device Under Test) assigned to the work item by querying the Asset API using the work item's DUT resource assignment. | Must |
| TI-07 | The test script SHALL extract the DUT's serial number, model, and relevant asset properties for use in the test result. | Must |
| TI-08 | The test script SHALL resolve the **system/minionId** for result and file linking. On a managed system: read the local minionId from `C:\ProgramData\National Instruments\salt\conf\minion_id` (Windows) or `/etc/salt/minion_id` (Linux). In developer mode (explicit credentials): use the system resource ID assigned to the work item (`resources.systems.selections[0].id`). | Must |
| TI-09 | The test script SHALL read **work item properties** (custom key-value pairs) and make them available as test parameters (e.g., test profile, environment conditions, customer-specific overrides). | Must |
| TI-10 | The test script SHALL validate that all required parameters (product specs, DUT identity, system match) are resolved before proceeding to test execution. If any are missing, it SHALL abort with a clear error message. | Must |
| TI-11 | In interactive mode, the test script SHOULD display a summary of resolved parameters (product, DUT serial, system, key specs) to the operator for confirmation before executing. In automated mode (work item ID passed via CLI), confirmation SHALL be skipped. | Should |
| TI-12 | When the work item ID is provided via CLI argument, the test script SHALL run in **fully automated mode** — no operator prompts or confirmations — so it can be executed remotely by SystemLink (e.g., via a system job, routine trigger, or remote shell command). | Must |
| TI-13 | In automated mode, if the product does not exist, the test script SHALL abort with an error (since no operator is available to provide a data sheet). Product creation requiring operator input is only available in interactive mode. | Must |

**Initialization flow:**

```
Operator enters Work Item ID
         │
         ▼
   Query Work Item ──────────────────────────────────────┐
         │                                               │
         ├── Read part number ──▶ Query Product API       │
         │                        │                      │
         │                  ┌─────┴──────┐               │
         │                  │            │               │
         │              Exists?      Not found?          │
         │                  │            │               │
         │            Load specs    Prompt for           │
         │            from product  data sheet /         │
         │            properties    manual entry         │
         │                  │            │               │
         │                  │      Create product        │
         │                  │      with specs            │
         │                  └─────┬──────┘               │
         │                        │                      │
         │                        ▼                      │
         │               Specs & limits resolved         │
         │                                               │
         ├── Read DUT assignment ──▶ Query Asset API     │
         │                           (serial, model,     │
         │                            properties)        │
         │                                               │
         ├── Read system assignment ──▶ Verify match     │
         │                              with local host  │
         │                                               │
         ├── Read work item properties ──▶ Test params   │
         │                                               │
         ▼                                               │
   Display parameter summary ◀───────────────────────────┘
         │
         ▼
   Operator confirms → Begin test execution
```

### 3.3 Test Execution

#### 3.3.1 Result Creation

| ID | Requirement | Priority |
|---|---|---|
| TE-01 | The test script SHALL create a **test result** in SystemLink Test Monitor at the start of execution, with status `RUNNING`, before any steps execute. | Must |
| TE-02 | The test result SHALL be pre-populated with the operator name, serial number, part number, host name, and start timestamp resolved during initialization (Section 3.2). | Must |
| TE-03 | The test script SHALL record the total test time from start to finish and update the result's `totalTimeInSeconds` on completion. | Must |
| TE-04 | On completion, the test script SHALL update the result status to `PASSED` (all steps passed), `FAILED` (one or more steps failed), or `ERRORED` (unrecoverable error). | Must |
| TE-05 | The test script SHALL handle hardware communication errors gracefully and report an `ERRORED` status with diagnostic details rather than crashing silently. | Must |

#### 3.3.2 Step Execution and Logging

| ID | Requirement | Priority |
|---|---|---|
| TE-10 | The test script SHALL execute one or more **test steps** sequentially, each representing a discrete measurement or check. | Must |
| TE-11 | For each step, the test script SHALL log the **inputs** — the stimulus or configuration applied to the DUT (e.g., input voltage, load current, frequency, temperature setpoint). Inputs SHALL be stored as step properties with an `input.` key prefix. | Must |
| TE-12 | For each step, the test script SHALL log the **outputs** — the raw response read from the DUT (e.g., measured voltage, current draw, signal amplitude). Outputs SHALL be stored as step properties with an `output.` key prefix. | Must |
| TE-13 | For each step, the test script SHALL record a **measurement** — the primary value under evaluation, derived from the output (may be the output itself or a computed value such as gain, efficiency, or error margin). | Must |
| TE-14 | For each step, the test script SHALL record the **limits** used to evaluate the measurement: low limit, high limit, and/or expected value, along with the comparison type. Limits SHALL be sourced from the product specs resolved during initialization. | Must |
| TE-15 | Each step SHALL have a **status** (`PASSED`, `FAILED`, `ERRORED`, `SKIPPED`) determined by comparing the measurement against its limits. | Must |
| TE-16 | Each step SHALL record **units** for the measurement and limits (e.g., `V`, `A`, `Ω`, `°C`, `Hz`, `dB`). | Must |
| TE-17 | The test script SHALL support parameterized test configurations — step limits and inputs SHALL be driven by the product specifications and work item properties, not hard-coded. | Must |
| TE-18 | The test script SHALL continue executing remaining steps after a step failure (do not abort on first failure) unless the failure is safety-critical. | Must |
| TE-19 | Each step SHALL record its own execution duration. | Should |
| TE-20 | The test script SHOULD log step-level timestamps (start and end) as step properties for traceability. | Should |

#### 3.3.3 Step Data Example

A single test step record SHALL capture the following data:

```
Step: "Output Voltage Under Load"
  Inputs:
    input.supply_voltage = 12.0 V
    input.load_current   = 2.5 A
    input.temperature    = 25.0 °C
  Outputs:
    output.raw_voltage   = 4.98 V
    output.ripple_mv     = 12.3 mV
  Measurement:
    value      = 4.98
    units      = "V"
    lowLimit   = 4.75
    highLimit  = 5.25
    comparison = GELE (≥ low, ≤ high)
  Status: PASSED
  Duration: 1.23 s
```

### 3.4 Result Reporting to Test Monitor

| ID | Requirement | Priority |
|---|---|---|
| RR-01 | The test script SHALL create a test result in SystemLink Test Monitor for every test execution. | Must |
| RR-02 | The test result SHALL include: program name, status (PASSED/FAILED/ERRORED), serial number, part number, operator, host name, start time, and total time. | Must |
| RR-03 | The test result SHALL contain one or more test steps, each with: step name, step type, status, and measurement value. | Must |
| RR-04 | Parametric test steps SHALL include numeric low limit, high limit, and units where applicable. | Must |
| RR-05 | The test result SHALL be associated with the correct SystemLink workspace. | Must |
| RR-06 | The test script SHOULD attach relevant properties (e.g., firmware version, fixture ID, test station) as key-value pairs on the result. | Should |
| RR-07 | The test script SHALL associate the Test Monitor product resolved during initialization (see TI-03 through TI-05) with the test result. | Must |
| RR-08 | The test result SHALL include a property `workItemId` set to the originating work item's ID, linking the result back to the work item for traceability and dashboard queries. | Must |

### 3.5 File and Artifact Management

| ID | Requirement | Priority |
|---|---|---|
| FA-01 | The test script SHALL upload **all** files generated during the test (logs, waveforms, screenshots, raw data, reports) to the SystemLink File Service. | Must |
| FA-02 | Each uploaded file SHALL be linked to the test result by storing the file's SystemLink file ID in a result property (`fileIds` — a comma-separated list of file IDs). | Must |
| FA-03 | Each uploaded file SHALL include metadata properties: `resultId` (the associated test result ID), `workItemId`, `minionId` (the SystemLink system/minion ID of the test system that generated the file), workspace, file type/category, and upload timestamp. | Must |
| FA-04 | The test result SHALL include a property `fileIds` containing the IDs of all uploaded files, enabling forward lookup from result to files. | Must |
| FA-05 | The test script SHOULD NOT upload files larger than 50 MB without chunked upload or compression. | Should |

### 3.6 Asset and DUT Tracking

| ID | Requirement | Priority |
|---|---|---|
| AT-01 | The test script SHOULD query the Asset service to verify that the DUT serial number is a registered asset before testing. | Should |
| AT-02 | The test script SHOULD verify that test fixtures and instruments have a valid calibration status (not PAST_RECOMMENDED_DUE_DATE) before executing tests. | Should |
| AT-03 | The test script MAY update asset properties (e.g., last test date, firmware version) after a successful test. | May |

### 3.7 Real-Time Status via Tags

| ID | Requirement | Priority |
|---|---|---|
| RT-01 | The test script SHOULD write a SystemLink tag indicating the current test state (IDLE, RUNNING, PASS, FAIL, ERROR) for dashboard visibility. | Should |
| RT-02 | The test script MAY write measurement values to tags in real time for live monitoring during long-running tests. | May |
| RT-03 | Tag paths SHALL follow a consistent naming convention: `<station>.<test-program>.<metric>`. | Must (if RT-01 or RT-02 is implemented) |

### 3.8 SystemLink Python API Usage

All communication with the SystemLink server SHALL use the `nisystemlink-clients` Python SDK. Direct HTTP requests (e.g., via `requests`, `httpx`, or `urllib`) to SystemLink REST endpoints are **prohibited**.

| ID | Requirement | Priority |
|---|---|---|
| API-01 | The application SHALL use the `nisystemlink-clients` Python package as the exclusive interface for all SystemLink server communication. | Must |
| API-02 | The application SHALL NOT make direct HTTP/REST calls to SystemLink APIs. All interactions must go through the SDK's typed client classes. | Must |
| API-03 | The application SHALL use `TestMonitorClient` for creating and updating test results, test steps, and products. | Must |
| API-04 | The application SHALL use the work item / work order client from `nisystemlink-clients` for querying, updating, and transitioning work items. | Must |
| API-05 | The application SHALL use `AssetManagementClient` for querying DUT assets, fixtures, and calibration status. | Must |
| API-06 | The application SHALL use `TagClient` for reading and writing real-time tags. | Must (if tags are used) |
| API-07 | The application SHALL use `FileClient` for uploading and managing supporting files. | Must (if file upload is used) |
| API-08 | The application SHALL configure the SDK's `HttpConfiguration` (server URL, API key) once at startup and pass it to all client instances. | Must |
| API-09 | The application SHALL rely on the SDK's built-in error handling and model classes (e.g., `TestResult`, `TestStep`, `Product`) rather than constructing raw JSON payloads. | Must |

---

## 4. Non-Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| NF-01 | API credentials (API keys) SHALL NOT be hard-coded in test scripts. They must be provided via environment variables, configuration files with restricted permissions, or SystemLink system credentials. | Must |
| NF-02 | The test script SHALL retry transient HTTP errors (429, 500, 502, 503) with exponential backoff, up to 3 attempts. | Must |
| NF-03 | The test script SHALL complete result upload within 30 seconds of test completion under normal network conditions. | Must |
| NF-04 | The integration SHALL NOT require SystemLink server connectivity to execute the test logic itself; results should be queued locally if the server is unreachable. | Should |
| NF-05 | The test script SHALL log all SystemLink API interactions (request, response status, timing) for troubleshooting. | Must |
| NF-06 | The integration SHALL be compatible with headless (no GUI) execution on both Windows and Linux test systems. | Must |

### 4.1 Packaging and Deployment

The Python application SHALL be packaged as an NI Package (.nipkg) so it can be uploaded to a SystemLink feed and deployed to test systems via NI Package Manager.

| ID | Requirement | Priority |
|---|---|---|
| PK-01 | The application SHALL be packaged as a `.nipkg` file suitable for distribution through a SystemLink package feed. | Must |
| PK-02 | The package SHALL include the Python application source, a bundled or pinned Python virtual environment (or a dependency manifest), and any required configuration files. | Must |
| PK-03 | The package SHALL define an install location on the target system (e.g., `C:\Program Files\<vendor>\<app-name>` on Windows, `/usr/local/<app-name>` on Linux RT). | Must |
| PK-04 | The package SHALL declare dependencies on the Python runtime and `nisystemlink-clients` package so NI Package Manager can resolve them during installation. | Must |
| PK-05 | The package SHALL include post-install scripts to set up the Python environment (install pip dependencies from a requirements file) if a bundled virtual environment is not included. | Must |
| PK-06 | The package SHALL be versioned using semantic versioning (e.g., `1.0.0`) embedded in the package metadata. | Must |
| PK-07 | The package SHALL be uploadable to a SystemLink feed via `slcli feed package upload` or the SystemLink Feed Management API. | Must |
| PK-08 | Once published to a feed, the package SHALL be deployable to target test systems using SystemLink's software deployment (system jobs / NI Package Manager). | Must |
| PK-09 | The package SHOULD include an uninstall script that cleanly removes the application and its virtual environment from the target system. | Should |
| PK-10 | The build process SHALL produce the `.nipkg` from a repeatable CI/CD pipeline (e.g., GitHub Actions, Jenkins) without manual intervention. | Should |

### 4.2 Work Item Template Provisioning

The CI/CD pipeline SHALL create (or update) a SystemLink work item template so that operators can schedule and configure test runs for this application directly from the SystemLink UI.

| ID | Requirement | Priority |
|---|---|---|
| WT-01 | The pipeline SHALL create a work item template of type `testplan` in SystemLink for this test application. | Must |
| WT-02 | The template name SHALL match the application/test program name so operators can identify it (e.g., `"BatteryCapacityTest"`). | Must |
| WT-03 | The template SHALL define a **resource requirement** for at least one system (the test station that will execute the test). | Must |
| WT-04 | The template SHOULD define resource requirements for fixtures and/or DUTs as applicable to the test. | Should |
| WT-05 | The template SHALL include **configurable properties** that map to test parameters (e.g., part number, test profile, environment conditions, customer-specific overrides), allowing operators to set values when creating a work item from the template. | Must |
| WT-06 | The template SHALL include a `description` and `summary` documenting the test's purpose, required equipment, and configurable parameters. | Must |
| WT-07 | The template SHALL be associated with a workflow that defines the valid state transitions for the test plan (e.g., NEW → SCHEDULED → IN_PROGRESS → COMPLETED / FAILED). | Should |
| WT-08 | The template definition SHALL be stored as a version-controlled JSON file in the application's source repository (e.g., `deploy/work-item-template.json`). | Must |
| WT-09 | The pipeline SHALL use `slcli workitem template create` (or update if it already exists) to provision the template to the target SystemLink server. | Must |
| WT-10 | The pipeline SHALL provision the template to the same workspace used for the application's test results and feed. | Must |
| WT-11 | The template version SHALL be kept in sync with the application version — when the application is updated and new parameters are added, the template SHALL be updated accordingly. | Must |
| WT-12 | The template SHALL include a **`partNumbers`** array (not `partNumberFilter`) that restricts it to the specific product the test is designed for. Only work items for that part number SHALL be creatable from this template. Example: `"partNumbers": ["B0CG1KL3RC"]`. | Must |

---

## 5. Data Flow

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  SystemLink  │────▶│  Python Test     │────▶│  SystemLink         │
│  Work Item   │     │  Script          │     │  Test Monitor       │
│  (assigned)  │     │                  │     │  (result + steps)   │
└─────────────┘     │  1. Query work   │     └─────────────────────┘
                    │     item          │              │
                    │  2. Read config   │              ▼
                    │  3. Run test      │     ┌─────────────────────┐
                    │  4. Publish       │     │  SystemLink         │
                    │     result        │     │  File Service       │
                    │  5. Upload files  │     │  (logs, waveforms)  │
                    │  6. Update work   │     └─────────────────────┘
                    │     item state    │
                    │  7. Update tags   │     ┌─────────────────────┐
                    └──────────────────┘     │  SystemLink Tags    │
                                             │  (real-time status) │
                                             └─────────────────────┘
```

---

## 6. Test Result Schema

Each test result published to SystemLink SHALL conform to this structure:

| Field | Type | Required | Example |
|---|---|---|---|
| `programName` | string | Yes | `"BatteryCapacityTest_v2"` |
| `status` | enum | Yes | `PASSED`, `FAILED`, `ERRORED` |
| `serialNumber` | string | Yes | `"SN-2026-00142"` |
| `partNumber` | string | Yes | `"P-BAT-001"` |
| `operator` | string | Yes | `"jsmith"` |
| `hostName` | string | Yes | Test system hostname |
| `startedAt` | ISO 8601 | Yes | `"2026-04-16T14:30:00Z"` |
| `totalTimeInSeconds` | float | Yes | `45.3` |
| `properties` | dict | Yes | `{"workItemId": "WI-abc123", "fixtureId": "FX-01", "fwVersion": "3.2.1"}` |
| `keywords` | list | No | `["production", "battery"]` |

Required result **properties**:

| Property Key | Description | Example |
|---|---|---|
| `workItemId` | The SystemLink work item ID that initiated this test run. Used to link results back to the originating work order. | `"WI-abc123"` |

Each test step SHALL conform to:

| Field | Type | Required | Example |
|---|---|---|---|
| `name` | string | Yes | `"Output Voltage Under Load"` |
| `stepType` | string | Yes | `"NumericLimit"`, `"StringValue"`, `"PassFail"` |
| `status` | enum | Yes | `PASSED`, `FAILED`, `ERRORED`, `SKIPPED` |
| `measurement` | float/string | Yes | `4.98` |
| `lowLimit` | float | Conditional | `4.75` |
| `highLimit` | float | Conditional | `5.25` |
| `units` | string | Yes | `"V"` |
| `comparisonType` | string | Conditional | `"GELE"` (≥ low, ≤ high), `"EQ"`, `"GT"`, `"LT"` |
| `properties` | dict | Yes | See inputs/outputs below |

Step **properties** SHALL include the following key-value pairs:

| Property Key Pattern | Description | Example |
|---|---|---|
| `input.<name>` | Stimulus or configuration applied to the DUT for this step | `"input.supply_voltage": "12.0 V"` |
| `output.<name>` | Raw response or reading from the DUT | `"output.raw_voltage": "4.98 V"` |
| `step.startedAt` | Step start timestamp (ISO 8601) | `"2026-04-16T14:30:05Z"` |
| `step.duration` | Step execution time in seconds | `"1.23"` |
| `step.limitSource` | Where limits originated | `"product:P-BAT-001"` |

---

## 7. Error Handling Matrix

| Scenario | Expected Behavior | Result Status |
|---|---|---|
| Test step measurement out of limits | Record step as FAILED, continue remaining steps | FAILED |
| Hardware communication timeout | Retry once, then abort with details in result | ERRORED |
| SystemLink server unreachable | Queue result locally, retry upload on next cycle | N/A (deferred) |
| Invalid work item state transition | Log warning, continue with result upload | Unaffected |
| Missing serial number or part number | Abort test, do not create partial result | No result created |
| API key expired or unauthorized | Log error, halt execution, alert operator | No result created |

---

## 8. SDK Implementation Notes

These notes capture verified SDK behaviors from the `nisystemlink-clients` package that are critical for correct implementation.

| Topic | Detail |
|---|---|
| `CreateStepRequest.step_id` | **Required field**. Must set `step_id=str(uuid.uuid4())` on every step. |
| `FileClient.upload_file(file=...)` | The `file` parameter takes a `BinaryIO` object (e.g., `open(path, "rb")`), **not** a file path. |
| `upload_file()` return value | Returns a `str` (file ID) directly, **not** an object with `.id`. |
| `Measurement` fields | All fields (`measurement`, `lowLimit`, `highLimit`, `units`) are **strings**, not numbers. |
| `StatusType` usage | Use `StatusType.PASSED` enum, not string `"PASSED"`. For `Measurement.status`, use `status_type.value`. |
| `Status` wrapper | Step and result status uses `Status(status_type=StatusType.PASSED)`, not `StatusType` directly. |
| Product properties | May not contain all `spec.*` keys. Always fall back to `PRODUCT_SPECS` defaults. |
| Work item state strings | Use string values for state: `"IN_PROGRESS"`, `"CLOSED"`, not enum values. |
| `HttpConfiguration` with `None` | Passing `None` to client constructors triggers auto-discovery on managed systems. |
| Work item template `partNumbers` | Use `partNumbers` (array of strings), **not** `partNumberFilter` (string). |

---

## 9. Acceptance Criteria

1. A Python test script can query, claim, and close a SystemLink work item end-to-end.
2. Every completed test run produces a structured result visible in the Test Monitor UI with correct status, steps, limits, and measurements.
3. Supporting files (if any) are uploaded and traceable back to the originating test result.
4. No API credentials are exposed in source code or logs.
5. The test script recovers gracefully from transient server errors without data loss.
6. The test supports three execution modes: interactive, automated (headless), and developer (explicit credentials).
7. MinionId is correctly resolved from local file (managed) or work item resource (dev mode).
6. The integration runs on both Windows and Linux without modification.
7. The application is packaged as a `.nipkg`, uploadable to a SystemLink feed, and deployable to a test system via NI Package Manager.
8. The CI/CD pipeline provisions a `testplan` work item template that allows operators to schedule and configure test runs from the SystemLink UI.
