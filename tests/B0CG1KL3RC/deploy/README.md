# Deploy Ops

Use `ops.py` as the single entrypoint for deploy and remote execution tasks.

## Canonical Commands

Install package (uses `pkg.install`, no `cmd.run`):

```powershell
python ops.py install-package --alias "Josh's Laptop" --package 18650-battery-test --version 1.0.1.12
```

Run test:

```powershell
python ops.py run-test --alias "Josh's Laptop" --work-item-id 3863530
```

Run test with UTF-8 environment override:

```powershell
python ops.py run-test --alias "NI_PXIe-8880--SN-031062CE--MAC-00-80-2F-16-5C-C1" --work-item-id 3863530 --cmd-prefix "set PYTHONUTF8=1"
```

Run test with `-X utf8`:

```powershell
python ops.py run-test --alias "NI_PXIe-8880--SN-031062CE--MAC-00-80-2F-16-5C-C1" --work-item-id 3863530 --cmd-prefix "set PYTHONUTF8=0" --python-extra-args "-X utf8"
```

Apply state:

```powershell
python ops.py apply-state --alias "Josh's Laptop" --state-id 69e23b7aaf1edbfc5fdc4697
```

## Legacy Script Status

Legacy scripts are retained as compatibility wrappers and now delegate to `ops.py`:

- `install_package_job.py`
- `run_systemlink_job.py`
- `run_job_joshs_pxi.py`
- `run_test_workitem_3863530_pxi.py`
- `run_test_workitem_3863530_pxi_utf8.py`
- `run_test_workitem_3863530_pxi_xutf8.py`
