"""调试 pie-ext 错误"""
import urllib.request, urllib.parse, sys

BASE = 'http://127.0.0.1:5199'
path = r'C:\Users\HZ\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\work-mode-projects\6a2606e0a08f0c4691d79e6e\opendisksize'

try:
    url = BASE + '/api/viz/pie-ext?path=' + urllib.parse.quote(path) + '&limit=15'
    print('Requesting: ' + url)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as r:
        data = r.read().decode('utf-8')
        print('Status: 200 OK')
        print('Response: ' + data[:500])
except urllib.error.HTTPError as e:
    print('HTTP Error: {} {}'.format(e.code, e.reason))
    print('Response body:')
    print(e.read().decode('utf-8')[:2000])
except Exception as e:
    print('Error: {}'.format(e))
