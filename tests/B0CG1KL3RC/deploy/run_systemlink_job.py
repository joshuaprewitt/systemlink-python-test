import json
import time
import _deploy_state as d

STATE_ID = '69e23b7aaf1edbfc5fdc4697'

q = d.api_post('/nisysmgmt/v1/query-systems', {'take': 1000})
systems = [s for s in q.get('data', []) if isinstance(s, dict)]

target = None
for s in systems:
    alias = (s.get('alias') or '').lower()
    host = (s.get('hostname') or '').lower()
    if "josh's laptop" in alias or 'joshs laptop' in alias or 'josh laptop' in alias:
        target = s
        break

if target is None:
    for s in systems:
        alias = (s.get('alias') or '').lower()
        host = (s.get('hostname') or '').lower()
        if 'josh' in alias or 'josh' in host:
            target = s
            break

if target is None:
    raise SystemExit('No Josh system found')

print('Target system:', target.get('alias'), target.get('id'))

job_body = {
    'tgt': [target['id']],
    'fun': ['state.apply', 'system.get_reboot_required_witnessed'],
    'metadata': {
        'queued': True,
        'timeout': 86400,
    },
    'arg': [
        [STATE_ID, {'__kwarg__': True, 'test': False}],
        [],
    ],
}

created = d.api_post('/nisysmgmt/v1/jobs', job_body)
print('Create response:', json.dumps(created, indent=2))

jid = created.get('jid') if isinstance(created, dict) else None
if not jid:
    raise SystemExit('No jid returned from job create')

for i in range(1, 37):
    raw = d.api_get(f'/nisysmgmt/v1/jobs?jid={jid}')
    job = raw[0] if isinstance(raw, list) and raw else raw
    state = job.get('state', 'UNKNOWN') if isinstance(job, dict) else 'UNKNOWN'
    print(f'Poll {i}: {state}')
    if state in ('SUCCEEDED', 'FAILED', 'CANCELED', 'TIMED_OUT'):
        print('Final job:', json.dumps(job, indent=2))
        break
    time.sleep(5)
