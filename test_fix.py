"""测试 pie-ext 和 export 端点"""
import json, urllib.request, urllib.parse

BASE = 'http://127.0.0.1:5199'
path = 'C:\\Users\\HZ\\AppData\\Roaming\\TRAE SOLO CN\\ModularData\\ai-agent\\work-mode-projects\\6a2606e0a08f0c4691d79e6e\\opendisksize'

# 测试 pie-ext
try:
    r = urllib.request.urlopen(BASE + '/api/viz/pie-ext?path=' + urllib.parse.quote(path) + '&limit=15')
    data = json.loads(r.read().decode('utf-8'))
    types = data.get('data', [])
    total = data.get('total', '')
    print('✅ pie-ext OK: {} types, total={}'.format(len(types), total))
    for t in types[:5]:
        print('   - {}: {}'.format(t.get('name'), t.get('size_str')))
except Exception as e:
    print('❌ pie-ext ERROR: {}'.format(e))

# 测试 CSV 导出
try:
    r = urllib.request.urlopen(BASE + '/api/export?path=' + urllib.parse.quote(path) + '&format=csv')
    content = r.read()
    ctype = r.headers.get('Content-Type', '')
    print('✅ CSV OK: {} bytes, type={}'.format(len(content), ctype))
except Exception as e:
    print('❌ CSV ERROR: {}'.format(e))

# 测试 HTML 导出
try:
    r = urllib.request.urlopen(BASE + '/api/export?path=' + urllib.parse.quote(path) + '&format=html')
    content = r.read()
    ctype = r.headers.get('Content-Type', '')
    print('✅ HTML OK: {} bytes, type={}'.format(len(content), ctype))
except Exception as e:
    print('❌ HTML ERROR: {}'.format(e))

print('\n=== 所有端点测试完成 ===')
