import json
import time
import _deploy_state as d

STATE_ID = '69e23b7aaf1edbfc5fdc4697'
TARGET_ALIAS = "Josh's PXI"

q = d.api_post('/nisysmgmt/v1/query-systems', {'take': 1000})
systems = [s for s in q.get('data', []) if isinstance(s, dict)]
target = None
for s in systems:
    if (s.get('alias') or '').strip().lower() == TARGET_ALIAS.lower():
        target = s
        break

if target is None:
    for s in systems:
        if 'josh' in (s.get('alias') or '').lower() and 'pxi' in (s.get('alias') or '').lower():
            target = s
            break

if target is None:
    raise SystemExit('Could not find target system alias: ' + TARGET_ALIAS)

system_id = target['id']
print('Target:', target.get('alias'), system_id)

job_body = {
    'tgt': [system_id],
    'fun': ['state.apply', 'system.get_reboot_required_witnessed'],
    'metadata': {'queued': True, 'timeout': 86400},
    'arg': [[STATE_ID, {'__kwarg__': True, 'test': False}], []],
}

created = d.api_post('/nisysmgmt/v1/jobs', job_body)
print('Created job:', json.dumps(created, indent=2))

jid = created.get('jid') if isinstance(created, dict) else None
if not jid:
    raise SystemExit('No JID returned from job creation')

for i in range(1, 73):
    raw = d.api_get(f'/nisysmgmt/v1/jobs?jid={jid}')
    job = raw[0] if isinstance(raw, list) and raw else raw
    state = job.get('state', 'UNKNOWN') if isinstance(job, dict) else 'UNKNOWN'
    print(f'Poll {i}: {state}')
    if state in ('SUCCEEDED', 'FAILED', 'CANCELED', 'TIMED_OUT'):
        print('Final job:', json.dumps(job, indent=2)[:30000])
        break
    time.sleep(5)
