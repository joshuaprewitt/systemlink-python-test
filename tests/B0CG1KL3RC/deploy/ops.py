"""Unified CLI for package install, test execution, and state apply jobs."""

import argparse
import json

from job_ops import (
    build_cmd_run_job,
    build_pkg_install_job,
    build_state_apply_job,
    create_job,
    extract_result_id,
    find_system,
    poll_job,
)


def _handle_install_package(args: argparse.Namespace) -> int:
    target = find_system(args.alias)
    print('Target system:', target.get('alias'), target.get('id'))

    body = build_pkg_install_job(
        system_id=target['id'],
        package_name=args.package,
        version=args.version,
        timeout_seconds=args.timeout,
        reinstall=args.reinstall,
    )
    jid = create_job(body)
    print('Install job JID:', jid)

    final = poll_job(jid, poll_seconds=args.poll_seconds, max_polls=args.max_polls)
    print('Final job:')
    print(json.dumps(final, indent=2))
    return 0


def _handle_run_test(args: argparse.Namespace) -> int:
    target = find_system(args.alias)
    print('Target system:', target.get('alias'), target.get('id'))

    python_part = f'"{args.test_root}\\venv\\Scripts\\python.exe"'
    if args.python_extra_args:
        python_part = f"{python_part} {args.python_extra_args}"

    cmd = f'{python_part} "{args.test_root}\\main.py" --work-item-id {args.work_item_id}'
    if args.cmd_prefix:
        cmd = f'{args.cmd_prefix} && {cmd}'

    body = build_cmd_run_job(target['id'], cmd, timeout_seconds=args.timeout)

    jid = create_job(body)
    print('Run job JID:', jid)

    final = poll_job(jid, poll_seconds=args.poll_seconds, max_polls=args.max_polls)
    print('Final job:')
    print(json.dumps(final, indent=2))

    result_id = extract_result_id(final)
    if result_id:
        print('RESULT_ID', result_id)
    return 0


def _handle_apply_state(args: argparse.Namespace) -> int:
    target = find_system(args.alias)
    print('Target system:', target.get('alias'), target.get('id'))

    body = build_state_apply_job(
        system_id=target['id'],
        state_id=args.state_id,
        timeout_seconds=args.timeout,
        test=args.test,
    )
    jid = create_job(body)
    print('State-apply job JID:', jid)

    final = poll_job(jid, poll_seconds=args.poll_seconds, max_polls=args.max_polls)
    print('Final job:')
    print(json.dumps(final, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='Unified SystemLink deploy operations CLI')
    sub = parser.add_subparsers(dest='command', required=True)

    install = sub.add_parser('install-package', help='Install a package via pkg.install (no cmd.run)')
    install.add_argument('--alias', default="Josh's Laptop", help='System alias/hostname fragment')
    install.add_argument('--package', default='18650-battery-test', help='Package name')
    install.add_argument('--version', required=True, help='Package version (example: 1.0.1.12)')
    install.add_argument('--reinstall', action='store_true', help='Request reinstall in pkg.install')
    install.add_argument('--timeout', type=int, default=3600, help='Job timeout in seconds')
    install.add_argument('--poll-seconds', type=int, default=5, help='Polling interval')
    install.add_argument('--max-polls', type=int, default=180, help='Max poll iterations')
    install.set_defaults(func=_handle_install_package)

    run_test = sub.add_parser('run-test', help='Run the installed battery test remotely via cmd.run')
    run_test.add_argument('--alias', default="Josh's Laptop", help='System alias/hostname fragment')
    run_test.add_argument('--work-item-id', default='3863530', help='Work item ID for main.py')
    run_test.add_argument('--test-root', default='C:\\Program Files\\NI\\18650-battery-test', help='Installed test root path')
    run_test.add_argument('--cmd-prefix', default='', help='Optional command prefix (example: set PYTHONUTF8=1)')
    run_test.add_argument('--python-extra-args', default='', help='Optional args for python executable (example: -X utf8)')
    run_test.add_argument('--timeout', type=int, default=3600, help='Job timeout in seconds')
    run_test.add_argument('--poll-seconds', type=int, default=5, help='Polling interval')
    run_test.add_argument('--max-polls', type=int, default=180, help='Max poll iterations')
    run_test.set_defaults(func=_handle_run_test)

    state_apply = sub.add_parser('apply-state', help='Apply a state on a target system')
    state_apply.add_argument('--alias', default="Josh's Laptop", help='System alias/hostname fragment')
    state_apply.add_argument('--state-id', required=True, help='State ID to apply')
    state_apply.add_argument('--test', action='store_true', help='Run state.apply in test mode')
    state_apply.add_argument('--timeout', type=int, default=86400, help='Job timeout in seconds')
    state_apply.add_argument('--poll-seconds', type=int, default=5, help='Polling interval')
    state_apply.add_argument('--max-polls', type=int, default=180, help='Max poll iterations')
    state_apply.set_defaults(func=_handle_apply_state)

    args = parser.parse_args()
    return args.func(args)


if __name__ == '__main__':
    raise SystemExit(main())
