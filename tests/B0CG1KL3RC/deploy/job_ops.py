"""Shared helpers for Systems Manager job submission and polling."""

import json
import time

import _deploy_state as d
from nisystemlink.clients.core import HttpConfiguration
from nisystemlink.clients.testmonitor import TestMonitorClient
from nisystemlink.clients.testmonitor.models import UpdateResultRequest

TERMINAL_STATES = {"SUCCEEDED", "FAILED", "CANCELED", "TIMED_OUT"}


def find_system(alias_fragment: str) -> dict:
    """Find a target system by case-insensitive alias/hostname substring match."""
    query = d.api_post('/nisysmgmt/v1/query-systems', {'take': 1000})
    systems = [s for s in (query or {}).get('data', []) if isinstance(s, dict)]

    needle = alias_fragment.lower()
    for system in systems:
        system_id = (system.get('id') or '').lower()
        alias = (system.get('alias') or '').lower()
        host = (system.get('hostname') or '').lower()
        if needle in system_id or needle in alias or needle in host:
            return system

    raise SystemExit(f"No system found matching alias fragment: {alias_fragment}")


def create_job(job_body: dict) -> dict:
    """Create a Systems Manager job and return the full create response."""
    created = d.api_post('/nisysmgmt/v1/jobs', job_body)
    print('Create response:')
    print(json.dumps(created, indent=2))

    jid = created.get('jid') if isinstance(created, dict) else None
    if not jid:
        raise SystemExit('No jid returned from job creation')
    return created


def get_creator_login(create_response: dict) -> str | None:
    """Extract and normalize job creator display/login name from create metadata."""
    metadata = (create_response or {}).get('metadata') or {}
    value = (metadata.get('user_login') or '').strip()
    if not value:
        return None

    # Jobs API commonly returns display names as "Last, First".
    # Normalize to "First Last" for Test Monitor operator readability.
    if ',' in value:
        parts = [part.strip() for part in value.split(',') if part.strip()]
        if len(parts) >= 2:
            return ' '.join(parts[1:] + [parts[0]])

    return value


def poll_job(jid: str, poll_seconds: int = 5, max_polls: int = 180) -> dict:
    """Poll a job until terminal state or timeout."""
    for i in range(1, max_polls + 1):
        raw = d.api_get(f'/nisysmgmt/v1/jobs?jid={jid}')
        job = raw[0] if isinstance(raw, list) and raw else raw
        state = job.get('state', 'UNKNOWN') if isinstance(job, dict) else 'UNKNOWN'
        print(f'Poll {i}: {state}')
        if state in TERMINAL_STATES:
            return job if isinstance(job, dict) else {}
        time.sleep(poll_seconds)

    raise SystemExit('Timed out waiting for job completion')


def build_cmd_run_job(system_id: str, command: str, timeout_seconds: int = 3600) -> dict:
    """Build a cmd.run job body."""
    return {
        'tgt': [system_id],
        'fun': ['cmd.run'],
        'arg': [[command, {'__kwarg__': True, 'shell': 'cmd'}]],
        'metadata': {'queued': True, 'timeout': timeout_seconds},
    }


def build_state_apply_job(system_id: str, state_id: str, timeout_seconds: int = 86400, test: bool = False) -> dict:
    """Build a state.apply job body."""
    return {
        'tgt': [system_id],
        'fun': ['state.apply', 'system.get_reboot_required_witnessed'],
        'metadata': {'queued': True, 'timeout': timeout_seconds},
        'arg': [
            [state_id, {'__kwarg__': True, 'test': test}],
            [],
        ],
    }


def build_pkg_install_job(
    system_id: str,
    package_name: str,
    version: str,
    timeout_seconds: int = 3600,
    reinstall: bool = False,
) -> dict:
    """Build a package install job body using pkg.install (no cmd.run)."""
    return {
        'tgt': [system_id],
        'fun': ['pkg.install', 'system.get_reboot_required_witnessed', 'pkg.info_installed'],
        'metadata': {
            'queued': True,
            'timeout': timeout_seconds,
            'pkg': {
                package_name: {
                    'displayName': package_name,
                }
            },
            'refresh_minion_cache': {
                'packages': True,
            },
            'fun': [
                None,
                None,
                {
                    '_update_minion_db_col_root': 'packages.data',
                    '_update_minion_db_strip_data_on_success': True,
                },
            ],
        },
        'arg': [
            [
                {
                    '__kwarg__': True,
                    'pkgs': [{package_name: version}],
                    'refresh': True,
                    'reinstall': reinstall,
                    'install_recommends': True,
                    'restart_if_required': True,
                    'test': False,
                }
            ],
            [],
            [
                {
                    '__kwarg__': True,
                    'attr': [
                        'description',
                        'displayname',
                        'displayversion',
                        'group',
                        'packager',
                        'priority',
                        'releasenotes',
                        'url',
                        'uservisible',
                        'version',
                        'wininsttype',
                        'storeproduct',
                        'size',
                        'arch',
                    ],
                }
            ],
        ],
    }


def extract_result_id(job: dict) -> str | None:
    """Extract the result ID from cmd.run return text when present."""
    result = str((job or {}).get('result'))
    marker = 'Result: '
    idx = result.find(marker)
    if idx == -1:
        return None
    return result[idx + len(marker): idx + len(marker) + 36]


def update_result_operator(result_id: str, operator_name: str) -> None:
    """Patch the Test Monitor result operator after remote execution completes."""
    if not result_id or not operator_name:
        return

    tm_client = TestMonitorClient(
        HttpConfiguration(server_uri=d.SERVER, api_key=d.API_KEY)
    )
    tm_client.update_results(
        [
            UpdateResultRequest(
                id=result_id,
                operator=operator_name,
            )
        ]
    )
