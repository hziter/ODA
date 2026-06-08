"""OpenDiskSize 完整 API 测试"""
import json, time, urllib.request, urllib.error, urllib.parse, os

BASE = 'http://127.0.0.1:5199'
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
print(f'=== OpenDiskSize API 测试 ===')
print(f'测试路径: {PROJECT_DIR}\n')

all_ok = True

def api_get(path, timeout=30):
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            return 200, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e: return e.code, str(e)
    except Exception as e: return -1, str(e)

def api_post(path, data, timeout=30):
    try:
        req = urllib.request.Request(BASE + path, data=json.dumps(data).encode('utf-8'),
                                      headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e: return e.code, str(e)
    except Exception as e: return -1, str(e)

def test(name, status, data=None, expect_list=False, expect_dict=False, details=''):
    global all_ok
    ok = (status == 200)
    if ok and expect_list: ok = isinstance(data, list)
    if ok and expect_dict: ok = isinstance(data, dict)
    symbol = '✅' if ok else '❌'
    info = ''
    if isinstance(data, list): info = f' [{len(data)} 项]'
    elif isinstance(data, dict):
        if 'items' in data: info = f' [{len(data["items"])} items]'
        elif 'data' in data: info = f' [{len(data["data"])} types]'
        else: info = f' [keys: {", ".join(list(data.keys())[:4])}]'
    else: info = f' [{str(data)[:60]}]'
    print(f'{symbol} [{status:3d}] {name}{info} {details}')
    if not ok: all_ok = False
    return ok

# 1. 驱动器列表
s, d = api_get('/api/drives')
test('GET /api/drives (驱动器列表)', s, d, expect_list=True)

# 2. 启动扫描
s, d = api_post('/api/scan', {'path': PROJECT_DIR, 'max_depth': 99})
test('POST /api/scan (启动扫描)', s, d, expect_dict=True)
scan_id = d.get('scan_id') if isinstance(d, dict) else None
print(f'  scan_id = {scan_id}')

# 3. 等待扫描完成
time.sleep(2)
s, d = api_get(f'/api/scan/progress/{scan_id}', timeout=60)
if isinstance(d, dict):
    done = d.get('done', False)
    pct = d.get('current', 0)
    print(f'  扫描状态: done={done}, percent={pct}%')

# 4. 列表视图
s, d = api_get(f'/api/node/list?path={urllib.parse.quote(PROJECT_DIR)}&sort_by=size&sort_order=desc')
test('GET /api/node/list (文件/目录列表)', s, d, expect_dict=True)
if isinstance(d, dict) and d.get('items'):
    items = d['items']
    print(f'  首项: {items[0].get("name")} ({items[0].get("size_str")}, {items[0].get("ext") if not items[0].get("is_dir") else "目录"})')

# 5. Treemap
s, d = api_get(f'/api/viz/treemap?path={urllib.parse.quote(PROJECT_DIR)}&depth=2')
test('GET /api/viz/treemap (矩形树图)', s, d, expect_list=True)

# 6. Pie chart
s, d = api_get(f'/api/viz/pie-ext?path={urllib.parse.quote(PROJECT_DIR)}&limit=15')
test('GET /api/viz/pie-ext (文件类型饼图)', s, d, expect_dict=True)
if isinstance(d, dict):
    print(f'  total = {d.get("total")}')

# 7. Top folders
s, d = api_get(f'/api/viz/top-folders?path={urllib.parse.quote(PROJECT_DIR)}&limit=20')
test('GET /api/viz/top-folders (最大文件夹)', s, d, expect_list=True)

# 8. Top files
s, d = api_get(f'/api/viz/top-files?path={urllib.parse.quote(PROJECT_DIR)}&limit=20')
test('GET /api/viz/top-files (最大文件)', s, d, expect_list=True)

# 9. Large files search
s, d = api_get(f'/api/search/large-files?path={urllib.parse.quote(PROJECT_DIR)}&min_mb=0&limit=20')
test('GET /api/search/large-files (大文件搜索)', s, d, expect_list=True)

# 10. Old files search
s, d = api_get(f'/api/search/old-files?path={urllib.parse.quote(PROJECT_DIR)}&days=0&limit=20')
test('GET /api/search/old-files (老旧文件)', s, d, expect_list=True)

# 11. Duplicates search
s, d = api_get(f'/api/search/duplicates?path={urllib.parse.quote(PROJECT_DIR)}&limit=20')
test('GET /api/search/duplicates (重复文件)', s, d, expect_list=True)

# 12. Summary
s, d = api_get(f'/api/summary?path={urllib.parse.quote(PROJECT_DIR)}')
test('GET /api/summary (摘要信息)', s, d, expect_dict=True)
if isinstance(d, dict):
    print(f'  total_size: {d.get("total_size_str")}, files: {d.get("files")}, folders: {d.get("folders")}')

# 13. Export CSV
s, d = api_get(f'/api/export?path={urllib.parse.quote(PROJECT_DIR)}&format=csv')
test('GET /api/export?format=csv (CSV导出)', s, d)

# 14. Export HTML
s, d = api_get(f'/api/export?path={urllib.parse.quote(PROJECT_DIR)}&format=html')
test('GET /api/export?format=html (HTML导出)', s, d)

# 15. Frontend page
s, html = -1, ''
try:
    with urllib.request.urlopen(BASE + '/', timeout=10) as r:
        html = r.read().decode('utf-8')
        s = 200
except Exception as e:
    s = -1
test('GET / (首页加载)', s, html if len(str(html)) < 100 else str(len(html)) + ' bytes')

print(f'\n{"="*60}')
if all_ok:
    print('✅ 所有 API 端点正常工作!')
else:
    print('❌ 部分端点有问题，请检查上方输出')
print(f'{"="*60}')
print(f'\n在浏览器中打开: {BASE}')
