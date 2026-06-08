"""测试 OpenDiskSize API - 使用小目录"""
import json, time, urllib.request, urllib.error, urllib.parse, os

BASE = 'http://127.0.0.1:5199'
TEST_PATH = os.path.dirname(os.path.abspath(__file__))  # 项目目录
print(f'测试路径: {TEST_PATH}\n')

def api_get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=30) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e: return e.code, str(e)
    except Exception as e: return -1, str(e)

def api_post(path, data):
    try:
        req = urllib.request.Request(BASE + path, data=json.dumps(data).encode('utf-8'),
                                      headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e: return e.code, str(e)
    except Exception as e: return -1, str(e)

def test(name, status, expected_ok=True, data=None, details=''):
    ok = (status == 200) == expected_ok
    symbol = '✅' if ok else '❌'
    info = ''
    if isinstance(data, list): info = f' [{len(data)}项]'
    elif isinstance(data, dict):
        if 'items' in data: info = f' [{len(data["items"])}项]'
        elif 'data' in data: info = f' [{len(data["data"])}项]'
        else: info = f' [keys:{",".join(list(data.keys())[:4])}]'
    print(f'{symbol} [{status:3d}] {name}{info} {details}')
    return ok

results = []
print('=' * 60)

# 1. 驱动器
s, d = api_get('/api/drives'); results.append(test('驱动器列表', s, d))

# 2. 启动扫描
s, d = api_post('/api/scan', {'path': TEST_PATH, 'max_depth': 99});
if isinstance(d, dict) and 'scan_id' in d: scan_id = d['scan_id']; print(f'  scan_id={scan_id}')

# 等待扫描完成
time.sleep(3)
for i in range(5):
    status_data = api_get(f'/api/scan/progress/{scan_id}')[1]
    if isinstance(status_data, dict) and status_data.get('done'):
        print(f'  扫描完成: done=True, percent={status_data.get("current", 0)}%'); break
    time.sleep(2)

# 3. 列表
s, d = api_get(f'/api/node/list?path={urllib.parse.quote(TEST_PATH)}&sort_by=size&sort_order=desc'); results.append(test('', s, d))
print(f'  → items count: {len(d.get("items",[]))}' if isinstance(d,dict) and 'items' in d else '')

# 4. 可视化
for viz in ['treemap', 'pie-ext', 'top-folders', 'top-files']:
    s, d = api_get(f'/api/viz/{viz}?path={urllib.parse.quote(TEST_PATH)}&limit=20')
    items = d if isinstance(d, list) else (d.get('data') if isinstance(d, dict) else [])
    print(f'  → {viz}: {len(items)} 项')

# 5. 搜索
for search in ['large-files', 'old-files', 'duplicates']:
    s, d = api_get(f'/api/search/{search}?path={urllib.parse.quote(TEST_PATH)}&limit=20&min_mb=0')
    items = d if isinstance(d, list) else []
    print(f'  → {search}: {len(items)} 项')

print(f'\n{"="*60}')

# 6. 直接测试列表数据结构
print('\n=== 数据结构验证 ===')
s, d = api_get(f'/api/node/list?path={urllib.parse.quote(TEST_PATH)}&sort_by=size&sort_order=desc')
if isinstance(d, dict) and 'items' in d and len(d['items']) > 0:
    item = d['items'][0]
    print(f'首项: {item.get("name")}, size={item.get("size_str")}, is_dir={item.get("is_dir")}')
    print(f'完整结构: {",".join(item.keys())}')

print(f'\n{"="*60}')
print('测试完成!')
