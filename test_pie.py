"""直接测试 pie-ext 函数逻辑"""
import os
import sys
from collections import defaultdict

# 模拟 app.py 中的 get_pie_by_extension 逻辑
path = r'C:\Users\HZ\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\work-mode-projects\6a2606e0a08f0c4691d79e6e\opendisksize'

def get_file_ext(name):
    ext = os.path.splitext(name)[1].lower().strip('.')
    return ext if ext else '(无)'

def format_size_human(size_bytes):
    if size_bytes is None or size_bytes == 0:
        return '0 B'
    import math
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    i = int(math.floor(math.log(abs(size_bytes), 1024)))
    i = min(i, len(units) - 1)
    val = size_bytes / (1024 ** i)
    if i == 0:
        return f'{int(val)} {units[i]}'
    if val >= 100:
        return f'{val:.1f} {units[i]}'
    return f'{val:.2f} {units[i]}'

print(f'Testing path: {path}')
print()

ext_stats = defaultdict(lambda: {'size': 0, 'count': 0})
file_count = [0]
max_files = 100000
max_depth = 4

def walk(p, level):
    try:
        entries = list(os.scandir(p))[:500]
        for entry in entries:
            if file_count[0] >= max_files:
                return
            try:
                if entry.is_dir(follow_symlinks=False):
                    if level < max_depth:
                        walk(entry.path, level + 1)
                else:
                    st = entry.stat(follow_symlinks=False)
                    ext = get_file_ext(entry.name)
                    ext_stats[ext]['size'] += st.st_size
                    ext_stats[ext]['count'] += 1
                    file_count[0] += 1
            except (PermissionError, OSError) as e:
                print(f'  WARN: {e} at {entry.path}')
                continue
    except (PermissionError, OSError) as e:
        print(f'  WARN: cannot open {p}: {e}')
        pass

walk(path, 0)

sorted_items = sorted(ext_stats.items(), key=lambda kv: -kv[1]['size'])
total_size = sum(v['size'] for v in ext_stats.values())
print(f'Total files scanned: {file_count[0]}')
print(f'Unique extensions: {len(sorted_items)}')
print(f'Total size: {format_size_human(total_size)}')
print()

for idx, (ext, stats) in enumerate(sorted_items[:10]):
    pct = round(stats['size'] / total_size * 100, 1) if total_size else 0
    print(f'  {idx+1:2d}. {ext:15s} {format_size_human(stats["size"]):>12s} '
          f'({stats["count"]:4d} files, {pct:5.1f}%)')

print()
print('Success!')
