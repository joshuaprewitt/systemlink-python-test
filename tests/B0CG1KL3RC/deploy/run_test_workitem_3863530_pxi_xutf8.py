import json
import time
import _deploy_state as d

target = 'NI_PXIe-8880--SN-031062CE--MAC-00-80-2F-16-5C-C1'
work_item_id = '3863530'
cmd = 'set PYTHONUTF8=0 && "C:\\Program Files\\NI\\18650-battery-test\\venv\\Scripts\\python.exe" -X utf8 "C:\\Program Files\\NI\\18650-battery-test\\main.py" --work-item-id ' + work_item_id

job_body = {
    'tgt': [target],
    'fun': ['cmd.run'],
    'arg': [[cmd, {'__kwarg__': True, 'shell': 'cmd'}]],
    'metadata': {'queued': True, 'timeout': 3600},
}

created = d.api_post('/nisysmgmt/v1/jobs', job_body)
print('Created job:', json.dumps(created, indent=2))
jid = created.get('jid') if isinstance(created, dict) else None
if not jid:
    raise SystemExit('No JID returned')

for i in range(1, 241):
    raw = d.api_get(f'/nisysmgmt/v1/jobs?jid={jid}')
    job = raw[0] if isinstance(raw, list) and raw else raw
    state = job.get('state', 'UNKNOWN') if isinstance(job, dict) else 'UNKNOWN'
    print(f'Poll {i}: {state}')
    if state in ('SUCCEEDED', 'FAILED', 'CANCELED', 'TIMED_OUT'):
        print('Final job:', json.dumps(job, indent=2)[:40000])
        break
    time.sleep(5)
