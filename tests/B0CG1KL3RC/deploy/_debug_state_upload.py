"""Debug: try import-state and show full error."""
import json, ssl, uuid, pathlib, urllib.request, urllib.error

cfg_path = pathlib.Path.home() / '.config' / 'slcli' / 'config.json'
cfg = json.loads(cfg_path.read_text())
current = cfg.get('current-profile', 'default')
profile = cfg.get('profiles', {}).get(current, {})
server = profile.get('server', '').rstrip('/')
key = profile.get('api-key', '')
ctx = ssl.create_default_context()

sls = pathlib.Path(__file__).with_name('install.sls')
boundary = uuid.uuid4().hex
parts = []
for name, val in [
    ('Name', '18650 Battery Test Provisioning'),
    ('Description', 'test'),
    ('Distribution', 'WINDOWS'),
    ('Architecture', 'X64'),
]:
    parts.append(f'--{boundary}\r\n'.encode())
    parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
    parts.append(f'{val}\r\n'.encode())
file_bytes = sls.read_bytes()
parts.append(f'--{boundary}\r\n'.encode())
parts.append(f'Content-Disposition: form-data; name="File"; filename="install.sls"\r\n'.encode())
parts.append(b'Content-Type: application/octet-stream\r\n\r\n')
parts.append(file_bytes)
parts.append(f'\r\n--{boundary}--\r\n'.encode())
body = b''.join(parts)

req = urllib.request.Request(
    f'{server}/nisystemsstate/v1/import-state', data=body, method='POST'
)
req.add_header('x-ni-api-key', key)
req.add_header('User-Agent', 'SystemLink-CLI/1.0')
req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')

try:
    resp = urllib.request.urlopen(req, context=ctx)
    data = json.loads(resp.read())
    print('SUCCESS:', json.dumps(data, indent=2))
except urllib.error.HTTPError as e:
    print('ERROR', e.code)
    body = e.read().decode()
    print(body)
    # If it is a duplicate (conflict), try to find the existing ID from query
    if e.code in (400, 409):
        try:
            err_data = json.loads(body)
            print('name:', err_data.get('name'))
            print('message:', err_data.get('message'))
            print('resourceId:', err_data.get('resourceId'))
        except Exception:
            pass
