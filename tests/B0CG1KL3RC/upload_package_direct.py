import json
import ssl
import uuid
import urllib.request
import urllib.error
from pathlib import Path

feed_id = '170e7b9d-9126-4fdf-a884-f6e42ea180b2'
package_path = Path(r'c:\Github\systemlink-python-test\tests\B0CG1KL3RC\dist\18650-battery-test_1.0.0.20260420083348_windows_all.nipkg')
url = f'https://demo-api.lifecyclesolutions.ni.com/nifeed/v1/feeds/{feed_id}/packages'
boundary = uuid.uuid4().hex
file_bytes = package_path.read_bytes()
parts = []
parts.append(f'--{boundary}\r\n'.encode())
parts.append(b'Content-Disposition: form-data; name="package"; filename="18650-battery-test_1.0.0.20260420083348_windows_all.nipkg"\r\n')
parts.append(b'Content-Type: application/octet-stream\r\n\r\n')
parts.append(file_bytes)
parts.append(f'\r\n--{boundary}--\r\n'.encode())
body = b''.join(parts)
req = urllib.request.Request(url, data=body, method='POST')
req.add_header('x-ni-api-key', 'D_QX7SLNROWBVWJfas8k2MgbWvUjNZN9UXunz8mq-G')
req.add_header('User-Agent', 'SystemLink-CLI/1.0')
req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
ctx = ssl.create_default_context()
try:
    with urllib.request.urlopen(req, context=ctx) as resp:
        print(resp.read().decode())
except urllib.error.HTTPError as e:
    print('STATUS', e.code)
    print(e.read().decode())
