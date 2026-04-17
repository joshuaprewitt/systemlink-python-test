import json
import time
import _deploy_state as d

target = 'NI_PXIe-8880--SN-031062CE--MAC-00-80-2F-16-5C-C1'
cmd = "powershell -Command \"$p1=Test-Path 'C:\\Program Files\\NI\\18650-battery-test\\venv\\Scripts\\python.exe'; $p2=Test-Path 'C:\\Program Files\\NI\\18650-battery-test\\venv\\Scripts\\pip.exe'; $p3=Test-Path 'C:\\Program Files\\NI\\18650-battery-test\\requirements.txt'; Write-Output ('python={0}; pip={1}; req={2}' -f $p1,$p2,$p3)\""

job_body = {
    'tgt': [target],
    'fun': ['cmd.run'],
    'arg': [[cmd, {'__kwarg__': True, 'shell': 'cmd'}]],
    'metadata': {'queued': True, 'timeout': 300},
}

created = d.api_post('/nisysmgmt/v1/jobs', job_body)
print('Created:', json.dumps(created, indent=2))
jid = created.get('jid')

for i in range(1, 41):
    raw = d.api_get(f'/nisysmgmt/v1/jobs?jid={jid}')
    job = raw[0] if isinstance(raw, list) and raw else raw
    state = job.get('state', 'UNKNOWN') if isinstance(job, dict) else 'UNKNOWN'
    print(f'Poll {i}: {state}')
    if state in ('SUCCEEDED', 'FAILED', 'CANCELED', 'TIMED_OUT'):
        print(json.dumps(job, indent=2)[:20000])
        break
    time.sleep(3)
