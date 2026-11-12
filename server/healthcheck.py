import json, urllib.request
with urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=3) as response:
    body = json.load(response)
    if response.status != 200 or body.get('database') != 'ok' or body.get('status') != 'ok' or body.get('api_version') != 1 or not body.get('server_instance_id'):
        raise SystemExit(1)
