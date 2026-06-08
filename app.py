#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OppenDiskAnalysis (ODA) v2.0 - 磁盘空间分析软件
完全参考 TreeSize 专业版功能界面设计
"""

import os
import os.path
import threading
import time
import math
import json
import hashlib
from datetime import datetime
from collections import defaultdict

import psutil
from flask import Flask, jsonify, request, render_template, send_file

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# ═════════════════════════════════════════════════════════════════════════════
# 全局扫描缓存与状态管理
# ═════════════════════════════════════════════════════════════════════════════
SCAN_CACHE = {}          # scan_id -> {path, root_size, total_files, total_folders, scan_time, nodes}
SCAN_PROGRESS = {}       # scan_id -> {current, total, current_item, done, cancelled}
_next_scan_id = 0
_node_path_map = {}      # 辅助：path -> node（供列表查询）
_node_lock = threading.Lock()

# ═════════════════════════════════════════════════════════════════════════════
# 工具函数
# ═════════════════════════════════════════════════════════════════════════════
def format_size_human(size_bytes):
    """格式化字节数为可读字符串 (TreeSize 风格)"""
    if size_bytes is None or size_bytes == 0:
        return "0 B"
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    i = int(math.floor(math.log(abs(size_bytes), 1024)))
    i = min(i, len(units) - 1)
    val = size_bytes / (1024 ** i)
    if i == 0:
        return f"{int(val)} {units[i]}"
    if val >= 100:
        return f"{val:.1f} {units[i]}"
    return f"{val:.2f} {units[i]}"

def format_date(ts):
    """时间戳 -> YYYY-MM-DD HH:MM:SS"""
    try:
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    except:
        return "-"

def get_file_ext(name):
    """获取文件扩展名（小写）"""
    ext = os.path.splitext(name)[1].lower().strip('.')
    return ext if ext else "(无)"

# ═════════════════════════════════════════════════════════════════════════════
# 磁盘信息 API
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/api/drives')
def get_drives():
    """获取所有磁盘分区"""
    drives = []
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            drives.append({
                'device': part.device,
                'mountpoint': part.mountpoint,
                'fstype': part.fstype or 'Unknown',
                'total': usage.total,
                'used': usage.used,
                'free': usage.free,
                'percent': round(usage.percent, 1),
                'total_str': format_size_human(usage.total),
                'used_str': format_size_human(usage.used),
                'free_str': format_size_human(usage.free),
                'percent_int': round(usage.percent),
            })
        except Exception:
            drives.append({
                'device': part.device,
                'mountpoint': part.mountpoint,
                'fstype': part.fstype or 'Unknown',
                'total': 0, 'used': 0, 'free': 0, 'percent': 0,
                'total_str': '-', 'used_str': '-', 'free_str': '-',
                'percent_int': 0,
            })
    return jsonify(drives)

# ═════════════════════════════════════════════════════════════════════════════
# 扫描引擎 (TreeSize 风格: 异步后台扫描 + 节点树)
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/api/scan', methods=['POST'])
def start_scan():
    """启动扫描（快速返回，后台异步执行）"""
    global _next_scan_id
    data = request.get_json(silent=True) or {}
    path = data.get('path', '').strip()
    max_depth = int(data.get('max_depth', 99))

    if not path or not os.path.exists(path):
        return jsonify({'error': '路径不存在或无效', 'path': path}), 400

    scan_id = _next_scan_id
    _next_scan_id += 1

    SCAN_PROGRESS[scan_id] = {
        'current': 0, 'total': 100, 'current_item': path, 'done': False, 'cancelled': False
    }

    # 启动后台线程
    threading.Thread(target=_scan_worker, args=(scan_id, path, max_depth), daemon=True).start()

    return jsonify({'scan_id': scan_id, 'path': path, 'message': '扫描已启动'})


@app.route('/api/scan/progress/<int:scan_id>')
def get_scan_progress(scan_id):
    """轮询扫描进度"""
    progress = SCAN_PROGRESS.get(scan_id)
    if not progress:
        return jsonify({'error': '扫描ID无效'}), 404
    return jsonify(progress)


def _scan_worker(scan_id, root_path, max_depth):
    """
    TreeSize 风格扫描算法:
    - DFS 递归遍历所有子目录
    - 累计每个目录的 size/file_count/folder_count
    - 返回后序遍历结果
    - 带文件数限制，防止大目录无限扫描
    """
    start_time = time.time()
    root_node = {'name': os.path.basename(root_path) or root_path,
                 'path': root_path,
                 'is_dir': True,
                 'size': 0,
                 'allocated': 0,
                 'files': 0,
                 'folders': 0,
                 'children': [],
                 'modified': 0,
                 'created': 0}

    file_count = 0
    folder_count = 0
    processed = 0
    MAX_TOTAL_FILES = 200000  # 限制总共扫描文件数

    try:
        total_estimate = 50000
        stack = [(root_node, root_path, 0)]
        _node_path_map[root_path] = root_node

        while stack and file_count < MAX_TOTAL_FILES:
            if SCAN_PROGRESS.get(scan_id, {}).get('cancelled', False):
                break

            parent_node, dir_path, depth = stack.pop()
            children_list = []

            try:
                entries = list(os.scandir(dir_path))[:1000]  # 单层限制
            except (PermissionError, OSError):
                continue

            for entry in entries:
                try:
                    stat_info = entry.stat(follow_symlinks=False)
                except (PermissionError, OSError):
                    continue

                if entry.is_dir(follow_symlinks=False):
                    folder_count += 1
                    if depth < max_depth and folder_count < 20000:
                        child_node = {
                            'name': entry.name,
                            'path': entry.path,
                            'is_dir': True,
                            'size': 0,
                            'allocated': 0,
                            'files': 0,
                            'folders': 0,
                            'children': [],
                            'modified': stat_info.st_mtime,
                            'created': stat_info.st_ctime,
                        }
                        children_list.append(child_node)
                        stack.append((child_node, entry.path, depth + 1))
                        _node_path_map[entry.path] = child_node
                    else:
                        # 超过最大深度/子目录数上限，只计数
                        parent_node['folders'] += 1
                else:
                    file_count += 1
                    fsize = stat_info.st_size
                    falloc = getattr(stat_info, 'st_blocks', 0) * 512 or fsize
                    parent_node['files'] += 1
                    parent_node['size'] += fsize
                    parent_node['allocated'] += falloc

                processed += 1
                if processed % 200 == 0:
                    pct = min(99, int((processed / total_estimate) * 100))
                    SCAN_PROGRESS[scan_id]['current'] = pct
                    SCAN_PROGRESS[scan_id]['current_item'] = dir_path
                    SCAN_PROGRESS[scan_id]['total'] = total_estimate

            parent_node['children'] = children_list

        # 后序累加：将子目录的 size 逐层回传到父级
        # 使用非递归 post-order traversal
        def post_order_sum(node):
            for child in node['children']:
                if child['children']:
                    post_order_sum(child)
                node['size'] += child['size']
                node['allocated'] += child['allocated']
                node['files'] += child['files']
                node['folders'] += child['folders'] + 1

        post_order_sum(root_node)

        scan_elapsed = round(time.time() - start_time, 2)

        # 写入缓存
        SCAN_CACHE[scan_id] = {
            'root_path': root_path,
            'root_node': root_node,
            'total_files': file_count,
            'total_folders': folder_count,
            'root_size': root_node['size'],
            'root_allocated': root_node['allocated'],
            'scan_time': scan_elapsed,
        }

        SCAN_PROGRESS[scan_id]['done'] = True
        SCAN_PROGRESS[scan_id]['current'] = 100
        SCAN_PROGRESS[scan_id]['current_item'] = '扫描完成'

    except Exception as e:
        SCAN_PROGRESS[scan_id]['done'] = True
        SCAN_PROGRESS[scan_id]['current_item'] = '扫描错误: ' + str(e)


# ═════════════════════════════════════════════════════════════════════════════
# 树视图 + 列表视图 API (核心: 基于节点树)
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/api/node/list')
def get_node_children():
    """
    获取指定路径下的子节点（TreeSize 风格: 含递归文件夹大小）
    支持: 排序、过滤
    """
    path = request.args.get('path', '').strip()
    scan_id = request.args.get('scan_id', type=int)
    sort_by = request.args.get('sort_by', 'size')
    sort_order = request.args.get('sort_order', 'desc')
    filter_name = request.args.get('filter', '').strip().lower()
    ext_filter = request.args.get('ext', '').strip().lower()
    min_size = request.args.get('min_size', type=int, default=0)
    max_size = request.args.get('max_size', type=int, default=0)

    # 尝试从缓存获取节点；如无缓存则直接扫描当前目录
    target_node = None
    if scan_id is not None and scan_id in SCAN_CACHE:
        target_node = _node_path_map.get(path)
    if target_node is None:
        # 临时扫描单层
        target_node = _quick_scan(path)

    if not target_node:
        return jsonify({'items': [], 'total': 0, 'path': path, 'parent_size': 0}), 200

    items = list(target_node['children']) if target_node.get('children') else []
    parent_size = target_node.get('size', 0) or 1

    # 过滤：按文件名
    if filter_name:
        items = [i for i in items if filter_name in i['name'].lower()]
    # 过滤：按扩展名
    if ext_filter:
        allowed_ext = set(e.strip().lower().strip('.') for e in ext_filter.split(',') if e.strip())
        if allowed_ext:
            items = [i for i in items if i['is_dir'] or get_file_ext(i['name']) in allowed_ext]
    # 过滤：按大小
    if min_size > 0:
        items = [i for i in items if i.get('size', 0) >= min_size]
    if max_size > 0:
        items = [i for i in items if i.get('size', 0) <= max_size]

    # 排序
    reverse = sort_order.lower() == 'desc'
    if sort_by == 'name':
        items.sort(key=lambda x: x['name'].lower(), reverse=reverse)
    elif sort_by == 'type':
        items.sort(key=lambda x: (0 if x['is_dir'] else 1, get_file_ext(x['name'])), reverse=reverse)
    elif sort_by == 'size':
        items.sort(key=lambda x: x.get('size', 0), reverse=reverse)
    elif sort_by == 'allocated':
        items.sort(key=lambda x: x.get('allocated', 0), reverse=reverse)
    elif sort_by == 'files':
        items.sort(key=lambda x: x.get('files', 0), reverse=reverse)
    elif sort_by == 'folders':
        items.sort(key=lambda x: x.get('folders', 0), reverse=reverse)
    elif sort_by == 'modified':
        items.sort(key=lambda x: x.get('modified', 0), reverse=reverse)
    elif sort_by == 'percent':
        items.sort(key=lambda x: x.get('size', 0) / parent_size if parent_size else 0, reverse=reverse)

    result = []
    for item in items:
        size = item.get('size', 0)
        alloc = item.get('allocated', 0) or size
        pct = round((size / parent_size * 100), 1) if parent_size else 0.0
        result.append({
            'name': item['name'],
            'path': item['path'],
            'is_dir': item['is_dir'],
            'size': size,
            'size_str': format_size_human(size),
            'allocated': alloc,
            'allocated_str': format_size_human(alloc),
            'percent': pct,
            'files': item.get('files', 0) or 0,
            'folders': item.get('folders', 0) or 0,
            'modified': format_date(item.get('modified', 0)),
            'created': format_date(item.get('created', 0)),
            'ext': get_file_ext(item['name']) if not item['is_dir'] else '(目录)',
            'avg_file_size': format_size_human(int(size / item['files'])) if item['is_dir'] and item.get('files', 0) > 0 else '-',
        })

    return jsonify({
        'items': result,
        'total': len(result),
        'path': path,
        'parent_size': parent_size,
        'parent_size_str': format_size_human(parent_size),
    })


# ═════════════════════════════════════════════════════════════════════════════
# 快速扫描：带智能截断的递归大小计算
# ═════════════════════════════════════════════════════════════════════════════
_MAX_FILES_PER_SCAN = 2000  # 每个 _recursive_dir_size 调用的最大文件数（防止卡住大目录）
_MAX_ENTRIES_PER_DIR = 500  # 单层目录的最大条目数

def _quick_scan(path):
    """扫描单层目录，仅计算每个子目录的递归大小（用于 TreeView 节点展开）"""
    node = {'name': os.path.basename(path) or path, 'path': path,
            'is_dir': True, 'children': [], 'size': 0, 'allocated': 0, 'files': 0, 'folders': 0,
            'modified': 0, 'created': 0}
    try:
        entries = list(os.scandir(path))[:_MAX_ENTRIES_PER_DIR]
        for entry in entries:
            try:
                stat_info = entry.stat(follow_symlinks=False)
                if entry.is_dir(follow_symlinks=False):
                    # 智能深度：路径越深，深度越小
                    depth = 3
                    if len(path.split(os.sep)) > 4:
                        depth = 2
                    if len(path.split(os.sep)) > 6:
                        depth = 1
                    dsize, dalloc, dfiles, dfolders = _recursive_dir_size(entry.path, depth=depth)
                    child = {
                        'name': entry.name, 'path': entry.path, 'is_dir': True,
                        'size': dsize, 'allocated': dalloc, 'files': dfiles, 'folders': dfolders,
                        'modified': stat_info.st_mtime, 'created': stat_info.st_ctime, 'children': [],
                    }
                    node['children'].append(child)
                    node['size'] += dsize
                    node['allocated'] += dalloc
                    node['files'] += dfiles
                    node['folders'] += dfolders + 1
                else:
                    fsize = stat_info.st_size
                    falloc = getattr(stat_info, 'st_blocks', 0) * 512 or fsize
                    node['children'].append({
                        'name': entry.name, 'path': entry.path, 'is_dir': False,
                        'size': fsize, 'allocated': falloc, 'files': 0, 'folders': 0,
                        'modified': stat_info.st_mtime, 'created': stat_info.st_ctime,
                    })
                    node['size'] += fsize
                    node['allocated'] += falloc
                    node['files'] += 1
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass
    return node


def _recursive_dir_size(path, depth=3, _file_count=None):
    """快速计算目录总大小（限制深度 + 文件数上限，避免大目录过慢）"""
    if _file_count is None:
        _file_count = [0]
    total_size = 0
    total_alloc = 0
    total_files = 0
    total_folders = 0
    try:
        entries = os.scandir(path)
        count = 0
        for entry in entries:
            count += 1
            if count > _MAX_ENTRIES_PER_DIR:
                break
            if _file_count[0] > _MAX_FILES_PER_SCAN:
                break
            try:
                if entry.is_dir(follow_symlinks=False):
                    if depth > 0 and _file_count[0] <= _MAX_FILES_PER_SCAN:
                        s, a, f, d = _recursive_dir_size(entry.path, depth - 1, _file_count)
                        total_size += s
                        total_alloc += a
                        total_files += f
                        total_folders += d + 1
                else:
                    st = entry.stat(follow_symlinks=False)
                    total_size += st.st_size
                    total_alloc += getattr(st, 'st_blocks', 0) * 512 or st.st_size
                    total_files += 1
                    _file_count[0] += 1
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass
    return total_size, total_alloc, total_files, total_folders


# ═════════════════════════════════════════════════════════════════════════════
# Treemap / Pie / Bar / Sunburst 可视化数据
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/api/viz/treemap')
def get_treemap_data():
    path = request.args.get('path', '').strip()
    depth = int(request.args.get('depth', 2))
    min_size = int(request.args.get('min_size', 0))

    node = _node_path_map.get(path) or _quick_scan(path)
    if not node:
        return jsonify([])

    def build_tm(current, level):
        children = sorted(current.get('children', []), key=lambda x: x.get('size', 0), reverse=True)
        if min_size:
            children = [c for c in children if c.get('size', 0) >= min_size]
        if level >= depth:
            return [{'name': c['name'], 'value': c.get('size', 0), 'is_dir': c['is_dir']} for c in children]

        result = []
        for c in children[:80]:
            item = {'name': c['name'], 'value': c.get('size', 0), 'is_dir': c['is_dir'], 'path': c['path']}
            if c['is_dir'] and c.get('children'):
                item['children'] = build_tm(c, level + 1)
            result.append(item)
        return result

    # 根节点直接作为第一层返回子目录
    return jsonify(build_tm(node, 1))


@app.route('/api/viz/pie-ext')
def get_pie_by_extension():
    """按文件扩展名统计 (TreeSize: 文件类型饼图) - 带文件数限制"""
    path = request.args.get('path', '').strip()
    max_depth = int(request.args.get('depth', 4))
    limit = int(request.args.get('limit', 15))

    if not path:
        return jsonify([])

    ext_stats = defaultdict(lambda: {'size': 0, 'count': 0})
    file_count = [0]
    max_files = 100000  # 限制最多扫描 10 万个文件

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
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            pass
    walk(path, 0)

    sorted_items = sorted(ext_stats.items(), key=lambda kv: -kv[1]['size'])
    total_size = sum(v['size'] for v in ext_stats.values())

    result = []
    others = {'size': 0, 'count': 0}
    for idx, (ext, stats) in enumerate(sorted_items):
        if idx < limit:
            result.append({
                'name': ext,
                'value': stats['size'],
                'count': stats['count'],
                'size_str': format_size_human(stats['size']),
                'percent': round(stats['size'] / total_size * 100, 1) if total_size else 0,
            })
        else:
            others['size'] += stats['size']
            others['count'] += stats['count']

    if others['size'] > 0:
        result.append({
            'name': '其他',
            'value': others['size'],
            'count': others['count'],
            'size_str': format_size_human(others['size']),
            'percent': round(others['size'] / total_size * 100, 1) if total_size else 0,
        })

    return jsonify({'data': result, 'total': format_size_human(total_size), 'total_bytes': total_size})


@app.route('/api/viz/top-folders')
def get_top_folders():
    """最大文件夹柱状图 (TreeSize 风格 Top N)"""
    path = request.args.get('path', '').strip()
    limit = int(request.args.get('limit', 20))

    node = _node_path_map.get(path) or _quick_scan(path)
    if not node:
        return jsonify([])

    folders = [c for c in node.get('children', []) if c.get('is_dir')]
    folders.sort(key=lambda x: x.get('size', 0), reverse=True)
    top = folders[:limit]

    return jsonify([{
        'name': f['name'],
        'path': f['path'],
        'value': f.get('size', 0),
        'size_str': format_size_human(f.get('size', 0)),
        'files': f.get('files', 0),
        'folders': f.get('folders', 0),
    } for f in top])


@app.route('/api/viz/top-files')
def get_top_files():
    """最大文件 (Top N 大文件)"""
    path = request.args.get('path', '').strip()
    limit = int(request.args.get('limit', 50))

    node = _node_path_map.get(path) or _quick_scan(path)
    if not node:
        return jsonify([])

    files = [c for c in node.get('children', []) if not c.get('is_dir')]
    files.sort(key=lambda x: x.get('size', 0), reverse=True)
    top = files[:limit]

    return jsonify([{
        'name': f['name'],
        'path': f['path'],
        'value': f.get('size', 0),
        'size_str': format_size_human(f.get('size', 0)),
        'ext': get_file_ext(f['name']),
        'modified': format_date(f.get('modified', 0)),
    } for f in top])


# ═════════════════════════════════════════════════════════════════════════════
# 高级功能: 全局大文件查找, 重复文件检测, 老旧文件
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/api/search/large-files')
def search_large_files():
    """查找整个路径下的所有大文件 (TreeSize: 最大文件功能) - 带文件数限制"""
    path = request.args.get('path', '').strip()
    min_size_mb = int(request.args.get('min_mb', 10))
    limit = int(request.args.get('limit', 200))

    if not path or not os.path.exists(path):
        return jsonify([])

    min_bytes = min_size_mb * 1024 * 1024
    large_files = []
    scanned = [0]
    max_scan = 100000  # 限制扫描文件数

    def walk(p):
        try:
            entries = list(os.scandir(p))[:500]
            for entry in entries:
                if scanned[0] >= max_scan and len(large_files) >= limit:
                    return
                try:
                    if entry.is_dir(follow_symlinks=False):
                        walk(entry.path)
                    else:
                        st = entry.stat(follow_symlinks=False)
                        scanned[0] += 1
                        if st.st_size >= min_bytes:
                            large_files.append({
                                'name': entry.name, 'path': entry.path, 'size': st.st_size,
                                'size_str': format_size_human(st.st_size),
                                'ext': get_file_ext(entry.name),
                                'modified': format_date(st.st_mtime),
                            })
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            pass

    walk(path)
    large_files.sort(key=lambda x: x['size'], reverse=True)
    return jsonify(large_files[:limit])


@app.route('/api/search/old-files')
def search_old_files():
    """查找长期未修改的文件 - 带文件数限制"""
    path = request.args.get('path', '').strip()
    days = int(request.args.get('days', 365))
    limit = int(request.args.get('limit', 200))

    if not path or not os.path.exists(path):
        return jsonify([])

    threshold = time.time() - days * 86400
    old_files = []
    scanned = [0]
    max_scan = 100000

    def walk(p):
        try:
            entries = list(os.scandir(p))[:500]
            for entry in entries:
                if scanned[0] >= max_scan and len(old_files) >= limit:
                    return
                try:
                    if entry.is_dir(follow_symlinks=False):
                        walk(entry.path)
                    else:
                        st = entry.stat(follow_symlinks=False)
                        scanned[0] += 1
                        if st.st_mtime < threshold:
                            old_files.append({
                                'name': entry.name, 'path': entry.path, 'size': st.st_size,
                                'size_str': format_size_human(st.st_size),
                                'ext': get_file_ext(entry.name),
                                'modified': format_date(st.st_mtime),
                                'days_old': int((time.time() - st.st_mtime) / 86400),
                            })
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            pass

    walk(path)
    old_files.sort(key=lambda x: x['size'], reverse=True)
    return jsonify(old_files[:limit])


@app.route('/api/search/duplicates')
def search_duplicates():
    """
    查找重复文件 (TreeSize: 重复文件检测)
    快速算法: 先按 (size+ext) 分组, 然后对 >=2 项的组计算部分哈希
    - 带文件数限制，避免大目录扫描过慢
    """
    path = request.args.get('path', '').strip()
    limit = int(request.args.get('limit', 100))

    if not path or not os.path.exists(path):
        return jsonify([])

    # phase 1: 按 size+ext 分组
    size_groups = defaultdict(list)
    scanned = [0]
    max_scan = 50000  # 限制最多扫描 5 万个文件（重复检测计算量大）

    def walk(p):
        try:
            entries = list(os.scandir(p))[:500]
            for entry in entries:
                if scanned[0] >= max_scan and len(size_groups) >= 100:
                    return
                try:
                    if entry.is_dir(follow_symlinks=False):
                        walk(entry.path)
                    else:
                        st = entry.stat(follow_symlinks=False)
                        scanned[0] += 1
                        if st.st_size >= 4096:  # 忽略 4KB 以下
                            key = (st.st_size, get_file_ext(entry.name))
                            size_groups[key].append({'path': entry.path, 'name': entry.name,
                                                    'size': st.st_size, 'modified': st.st_mtime})
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            pass

    walk(path)

    # phase 2: 对有多个项的组，计算文件头部哈希 (前 64KB)
    hash_groups = defaultdict(list)
    for key, candidates in size_groups.items():
        if len(candidates) < 2:
            continue
        for cand in candidates:
            try:
                h = hashlib.md5()
                with open(cand['path'], 'rb') as f:
                    chunk = f.read(65536)
                    h.update(chunk)
                hash_groups[h.hexdigest()].append(cand)
            except (PermissionError, OSError):
                continue

    # phase 3: 返回至少含 2 个文件的分组
    duplicates = []
    for h, items in hash_groups.items():
        if len(items) >= 2:
            total_wasted = sum(i['size'] for i in items) - items[0]['size']
            duplicates.append({
                'hash': h, 'size': items[0]['size'],
                'size_str': format_size_human(items[0]['size']),
                'files': [{
                    'path': i['path'], 'name': i['name'],
                    'size_str': format_size_human(i['size']),
                    'modified': format_date(i['modified']),
                } for i in items],
                'count': len(items),
                'wasted_bytes': total_wasted,
                'wasted_str': format_size_human(total_wasted),
            })

    duplicates.sort(key=lambda x: -x['wasted_bytes'])
    return jsonify(duplicates[:limit])


# ═════════════════════════════════════════════════════════════════════════════
# 摘要 / 导出
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/api/summary')
def get_summary():
    """返回扫描结果摘要 (TreeSize 风格的文件/目录分布)"""
    path = request.args.get('path', '').strip()
    if not path or not os.path.exists(path):
        return jsonify({'error': '路径无效'}), 400

    node = _node_path_map.get(path) or _quick_scan(path)
    if not node:
        return jsonify({'error': '扫描失败'}), 500

    size = node.get('size', 0)
    files = node.get('files', 0)
    folders = node.get('folders', 0)

    # 顶层最大项 (Top 5)
    top = sorted(node.get('children', []), key=lambda c: c.get('size', 0), reverse=True)[:8]
    top_list = [{
        'name': c['name'], 'path': c['path'], 'size': c.get('size', 0),
        'size_str': format_size_human(c.get('size', 0)),
        'is_dir': c['is_dir'],
        'percent': round(c.get('size', 0) / size * 100, 1) if size else 0,
    } for c in top]

    return jsonify({
        'path': path,
        'total_size': size,
        'total_size_str': format_size_human(size),
        'total_allocated': format_size_human(node.get('allocated', size)),
        'files': files,
        'folders': folders,
        'items_count': len(node.get('children', [])),
        'avg_file_size': format_size_human(int(size / files)) if files > 0 else '0 B',
        'top_items': top_list,
    })


@app.route('/api/export')
def export_report():
    """导出 CSV / HTML 报告"""
    path = request.args.get('path', '').strip()
    fmt = request.args.get('format', 'csv')
    if not path or not os.path.exists(path):
        return jsonify({'error': '路径无效'}), 400

    node = _quick_scan(path)
    now = datetime.now()
    ts = now.strftime('%Y%m%d_%H%M%S')
    export_dir = os.path.join(os.path.dirname(__file__), 'exports')
    os.makedirs(export_dir, exist_ok=True)

    rows = _collect_flat_rows(node)

    if fmt == 'csv':
        filename = f'OppenDiskAnalysis_Export_{ts}.csv'
        filepath = os.path.join(export_dir, filename)
        _write_csv(filepath, path, rows, now)
    elif fmt == 'html':
        filename = f'OppenDiskAnalysis_Report_{ts}.html'
        filepath = os.path.join(export_dir, filename)
        _write_html(filepath, path, rows, now)
    else:
        return jsonify({'error': '不支持的格式'}), 400

    return send_file(filepath, as_attachment=True, download_name=filename, mimetype='text/html' if fmt == 'html' else 'text/csv')


def _collect_flat_rows(node, rows=None):
    """收集单层内容为列表"""
    if rows is None:
        rows = []
    for c in node.get('children', []):
        rows.append(c)
    return rows


def _write_csv(filepath, scan_path, rows, now):
    import csv
    with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['# OppenDiskAnalysis 磁盘分析报告'])
        w.writerow(['# 扫描路径:', scan_path])
        w.writerow(['# 生成时间:', now.strftime('%Y-%m-%d %H:%M:%S')])
        w.writerow(['名称', '路径', '类型', '大小(B)', '大小', '文件数', '子目录数', '修改时间', '属性'])
        for r in rows:
            w.writerow([
                r['name'], r['path'], '目录' if r.get('is_dir') else get_file_ext(r['name']),
                r.get('size', 0), format_size_human(r.get('size', 0)),
                r.get('files', 0), r.get('folders', 0),
                format_date(r.get('modified', 0)),
                'D' if r.get('is_dir') else '',
            ])


def _write_html(filepath, scan_path, rows, now):
    total = sum(r.get('size', 0) for r in rows)
    max_size = max((r.get('size', 0) for r in rows), default=1)

    rows.sort(key=lambda r: r.get('size', 0), reverse=True)

    body = f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>OppenDiskAnalysis 磁盘分析报告</title>
<style>
body {{ font-family: "Segoe UI", Arial, sans-serif; margin: 24px; color: #333; }}
h1 {{ color: #1565c0; border-bottom: 3px solid #1565c0; padding-bottom: 8px; }}
h2 {{ color: #1976d2; margin-top: 24px; }}
.summary {{ background: #e3f2fd; border-radius: 8px; padding: 16px; margin: 12px 0; }}
.summary table {{ border-collapse: collapse; width: 100%; }}
.summary td {{ padding: 6px 10px; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 12px; }}
th {{ background: #1976d2; color: #fff; padding: 8px 10px; text-align: left; font-size: 12px; }}
td {{ padding: 6px 10px; border-bottom: 1px solid #e0e0e0; font-size: 12px; }}
tr:hover {{ background: #f5f5f5; }}
.bar-cell {{ display: inline-block; background: #1976d2; height: 14px; border-radius: 2px; min-width: 2px; }}
.meta {{ color: #666; font-size: 12px; margin: 8px 0 24px; }}
</style></head>
<body>
<h1>📊 OppenDiskAnalysis 磁盘空间分析报告</h1>
<div class="meta">
<div>扫描路径: <strong>{scan_path}</strong></div>
<div>生成时间: <strong>{now.strftime('%Y-%m-%d %H:%M:%S')}</strong></div>
<div>扫描项数: <strong>{len(rows)}</strong> | 总大小: <strong>{format_size_human(total)}</strong></div>
</div>
<table><thead><tr>
<th>名称</th><th>类型</th><th style="text-align:right">大小</th><th style="text-align:right">占比</th><th>大小分布</th>
</tr></thead><tbody>
'''
    for r in rows[:500]:
        size = r.get('size', 0)
        pct = round(size / max_size * 100, 1) if max_size else 0
        total_pct = round(size / total * 100, 1) if total else 0
        type_label = '📁 目录' if r.get('is_dir') else f'📄 {get_file_ext(r["name"])}'
        body += f'<tr><td>{r["name"]}</td><td>{type_label}</td>'
        body += f'<td style="text-align:right">{format_size_human(size)}</td>'
        body += f'<td style="text-align:right">{total_pct}%</td>'
        body += f'<td><span class="bar-cell" style="width:{pct * 2}px"></span></td></tr>'

    body += '</tbody></table></body></html>'

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(body)


# ═════════════════════════════════════════════════════════════════════════════
# 前端根路由
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/')
def index():
    return render_template('index.html')


def _get_local_ips():
    """获取本机所有 IPv4 地址（用于显示外部访问地址）"""
    import socket
    ips = []
    try:
        # 首选方法: 获取所有 socket 地址
        hostname = socket.gethostname()
        try:
            addr_list = socket.getaddrinfo(hostname, None, socket.AF_INET)
            seen = set()
            for a in addr_list:
                ip = a[4][0]
                if ip not in seen and not ip.startswith('127.'):
                    seen.add(ip)
                    ips.append(ip)
        except Exception:
            pass
        # 备选方法: 连接外网查看出网地址
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            outbound_ip = s.getsockname()[0]
            s.close()
            if outbound_ip not in ips and not outbound_ip.startswith('127.'):
                ips.insert(0, outbound_ip)
        except Exception:
            pass
    except Exception:
        pass
    return ips


@app.route('/api/server-info')
def get_server_info():
    """返回服务器信息（前端用于提示用户可访问地址）"""
    import socket
    port = 5199
    hostname = socket.gethostname()
    ips = _get_local_ips()
    return jsonify({
        'hostname': hostname,
        'ips': ips,
        'port': port,
        'local_url': f'http://127.0.0.1:{port}',
        'lan_urls': [f'http://{ip}:{port}' for ip in ips],
        'platform': __import__('sys').platform,
        'scan_scope': 'server-side (扫描的是服务器端本机磁盘,不是浏览器所在的设备)',
        'note': '如需分析其他设备的磁盘,请在该设备上本地运行 ODA,或在服务器端挂载/映射其共享目录(如 \\\\192.168.1.100\\share)',
    })


if __name__ == '__main__':
    port = 5199
    hostname = __import__('socket').gethostname()
    ips = _get_local_ips()

    print("=" * 70)
    print("  📊 OppenDiskAnalysis (ODA) v2.0 - 磁盘空间分析软件")
    print("  ─────────────────────────────────────────────────────")
    print(f"  ▶ 本机访问 (localhost):   http://127.0.0.1:{port}")
    for ip in ips:
        print(f"  ▶ 局域网访问 (LAN):       http://{ip}:{port}")
    print("  ─────────────────────────────────────────────────────")
    print("  ⚠  安全提示:")
    print("     - 已允许外部设备访问（绑定 0.0.0.0）")
    print("     - ODA 扫描的是【运行此软件的电脑】的磁盘")
    print("     - 不是访问网页的那台设备的磁盘（浏览器安全限制）")
    print("     - 如需分析其他设备,请在该设备上运行 ODA")
    print("     - 或在本机以 UNC 路径扫描网络共享(如 \\\\192.168.1.100\\share)")
    print("  ─────────────────────────────────────────────────────")
    print(f"  ▶ 按 Ctrl+C 可停止服务")
    print("=" * 70)

    try:
        import webbrowser
        webbrowser.open(f'http://127.0.0.1:{port}')
    except Exception:
        pass

    # host='0.0.0.0' = 绑定所有网络接口,允许局域网访问
    # host='127.0.0.1' = 仅本地访问(旧配置)
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
