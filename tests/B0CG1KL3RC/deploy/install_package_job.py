import argparse
import json
import time

import _deploy_state as d


def _find_system(alias_fragment: str) -> dict:
    query = d.api_post('/nisysmgmt/v1/query-systems', {'take': 1000})
    systems = [s for s in (query or {}).get('data', []) if isinstance(s, dict)]

    needle = alias_fragment.lower()
    for system in systems:
        alias = (system.get('alias') or '').lower()
        host = (system.get('hostname') or '').lower()
        if needle in alias or needle in host:
            return system

    raise SystemExit(f"No system found matching alias fragment: {alias_fragment}")


def _submit_install_job(system_id: str, package_name: str, version: str, timeout_seconds: int) -> str:
    job_body = {
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
                    'reinstall': False,
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

    created = d.api_post('/nisysmgmt/v1/jobs', job_body)
    print('Create response:')
    print(json.dumps(created, indent=2))

    jid = created.get('jid') if isinstance(created, dict) else None
    if not jid:
        raise SystemExit('No jid returned from install job create')
    return jid


def _poll_job(jid: str, poll_seconds: int, max_polls: int) -> dict:
    for i in range(1, max_polls + 1):
        raw = d.api_get(f'/nisysmgmt/v1/jobs?jid={jid}')
        job = raw[0] if isinstance(raw, list) and raw else raw
        state = job.get('state', 'UNKNOWN') if isinstance(job, dict) else 'UNKNOWN'
        print(f'Poll {i}: {state}')
        if state in ('SUCCEEDED', 'FAILED', 'CANCELED', 'TIMED_OUT'):
            return job if isinstance(job, dict) else {}
        time.sleep(poll_seconds)
    raise SystemExit('Timed out waiting for install job completion')


def main() -> None:
    parser = argparse.ArgumentParser(description='Install a package via Systems Manager pkg.install job (no cmd.run).')
    parser.add_argument('--alias', default="Josh's Laptop", help='System alias/hostname fragment to target')
    parser.add_argument('--package', default='18650-battery-test', help='Package name to install')
    parser.add_argument('--version', required=True, help='Package version to install (example: 1.0.1.12)')
    parser.add_argument('--timeout', type=int, default=3600, help='Job timeout in seconds')
    parser.add_argument('--poll-seconds', type=int, default=5, help='Polling interval in seconds')
    parser.add_argument('--max-polls', type=int, default=180, help='Maximum polls before timeout')
    args = parser.parse_args()

    target = _find_system(args.alias)
    print('Target system:', target.get('alias'), target.get('id'))

    jid = _submit_install_job(
        system_id=target['id'],
        package_name=args.package,
        version=args.version,
        timeout_seconds=args.timeout,
    )
    print('Install job JID:', jid)

    final = _poll_job(jid, args.poll_seconds, args.max_polls)
    print('Final job:')
    print(json.dumps(final, indent=2))


if __name__ == '__main__':
    main()
