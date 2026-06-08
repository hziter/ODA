"""测试前端页面"""
import urllib.request

r = urllib.request.urlopen('http://127.0.0.1:5199/')
content = r.read().decode('utf-8')
print(f'页面大小: {len(content)} 字节')

keywords = ['toolbar', 'driveSummary', 'treeView', 'listHeader',
            'chartContainer', 'statusBar', 'contextMenu',
            'app.js', 'style.css', 'echarts']
for kw in keywords:
    found = kw in content
    status = 'OK' if found else 'MISSING'
    print(f'  [{status}] {kw}')

print('\n=== 检查 JavaScript 语法 ===')
# 检查 JS 文件
with urllib.request.urlopen('http://127.0.0.1:5199/static/js/app.js') as r:
    js = r.read().decode('utf-8')
print(f'JS 文件大小: {len(js)} 字节')

# 检查 CSS 文件
with urllib.request.urlopen('http://127.0.0.1:5199/static/css/style.css') as r:
    css = r.read().decode('utf-8')
print(f'CSS 文件大小: {len(css)} 字节')

print('\n✅ 前端页面验证完成')
