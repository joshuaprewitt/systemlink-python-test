import json
import time
import _deploy_state as d

target = 'NI_PXIe-8880--SN-031062CE--MAC-00-80-2F-16-5C-C1'
cmd = "powershell -Command \"$p='C:\\Program Files\\NI\\18650-battery-test\\execution.py'; $t=Get-Content -Raw $p; $t=$t -replace 'with open\(path, \"w\"\) as f:', 'with open(path, \"w\", encoding=\"utf-8\") as f:'; Set-Content -Encoding UTF8 $p $t; Write-Output 'patched'\""
job_body = {
  'tgt':[target],
  'fun':['cmd.run'],
  'arg': [[cmd, {'__kwarg__': True, 'shell':'cmd'}]],
  'metadata': {'queued': True, 'timeout': 300}
}
created = d.api_post('/nisysmgmt/v1/jobs', job_body)
print('Created patch job:', json.dumps(created, indent=2))
jid = created.get('jid')
for i in range(1,41):
  raw = d.api_get(f'/nisysmgmt/v1/jobs?jid={jid}')
  job = raw[0] if isinstance(raw,list) and raw else raw
  state = job.get('state','UNKNOWN') if isinstance(job,dict) else 'UNKNOWN'
  print(f'Poll {i}: {state}')
  if state in ('SUCCEEDED','FAILED','CANCELED','TIMED_OUT'):
    print('Final patch job:', json.dumps(job, indent=2)[:20000])
    break
  time.sleep(3)
