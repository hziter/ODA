/**
 * OppenDiskAnalysis (ODA) v2.0 - 前端交互主逻辑
 * TreeSize 风格三栏布局: 驱动器摘要+目录树 / 详细列表 / 可视化图表
 */
(function () {
  'use strict';

  // ========================= 全局状态 =========================
  const STATE = {
    currentPath: '',
    rootPath: '',
    scanId: null,
    scanTimer: null,
    view: 'treemap',
    sortBy: 'size',
    sortOrder: 'desc',
    filterText: '',
    extFilter: '',
    currentItems: [],
    currentContextPath: '',
    currentContextName: '',
    chartInstance: null,
    drives: [],
  };

  // ========================= 工具函数 =========================
  function formatSize(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
    const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    const val = bytes / Math.pow(1024, i);
    if (i === 0) return `${Math.round(val)} ${units[i]}`;
    if (val >= 100) return `${val.toFixed(1)} ${units[i]}`;
    return `${val.toFixed(2)} ${units[i]}`;
  }

  function escapeHtml(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function getFileIcon(name, isDir) {
    if (isDir) return '📁';
    const ext = name.split('.').pop().toLowerCase();
    const map = {
      exe: '⚙', dll: '⚙', sys: '⚙',
      zip: '📦', rar: '📦', '7z': '📦', tar: '📦', gz: '📦',
      jpg: '🖼', jpeg: '🖼', png: '🖼', gif: '🖼', bmp: '🖼', svg: '🖼', webp: '🖼',
      mp4: '🎬', avi: '🎬', mkv: '🎬', mov: '🎬', wmv: '🎬', flv: '🎬',
      mp3: '🎵', wav: '🎵', flac: '🎵', wma: '🎵', ogg: '🎵',
      pdf: '📄', doc: '📝', docx: '📝', rtf: '📝', txt: '📃', md: '📃', log: '📃',
      xls: '📊', xlsx: '📊', csv: '📊',
      ppt: '📑', pptx: '📑',
      iso: '💿', img: '💿',
      js: '⚡', ts: '⚡', jsx: '⚡', tsx: '⚡',
      html: '🌐', htm: '🌐', css: '🎨',
      py: '🐍', java: '☕', c: '⚙', cpp: '⚙', h: '⚙', cs: '⚙',
      json: '📋', yaml: '📋', yml: '📋', xml: '📋',
      ini: '⚙', cfg: '⚙', conf: '⚙',
      bak: '🔙', old: '🔙', tmp: '⏱', temp: '⏱',
    };
    return map[ext] || '📄';
  }

  function getPctColor(pct) {
    if (pct > 40) return 'large';
    if (pct > 15) return 'medium';
    return '';
  }

  function setStatus(text, iconState) {
    document.getElementById('statusText').textContent = text;
    const icon = document.getElementById('statusIcon');
    icon.className = iconState || '';
  }

  // ========================= 初始化 =========================
  function init() {
    initChart();
    loadDrives();
    loadServerInfo();
    bindEvents();
    startClock();
    setStatus('就绪 - 选择一个驱动器或输入路径', '');
  }

  async function loadServerInfo() {
    try {
      const res = await fetch('/api/server-info');
      const info = await res.json();
      document.getElementById('serverHostname').textContent = info.hostname || '未知';
      document.getElementById('serverPlatform').textContent =
        '平台: ' + (info.platform || 'unknown') + ' · 端口: ' + (info.port || 5199);
      document.getElementById('localUrl').textContent = info.local_url || 'http://127.0.0.1:5199';
      const lanUrls = info.lan_urls || [];
      if (lanUrls.length === 0) {
        document.getElementById('lanUrls').innerHTML =
          '<span style="color:#888;">未检测到局域网 IP（当前可能只有本机可访问）</span>';
      } else {
        document.getElementById('lanUrls').innerHTML = lanUrls
          .map((u) => '<code style="background:#fff;padding:4px 10px;border-radius:4px;display:inline-block;margin:2px 4px 2px 0;">' + u + '</code>')
          .join('<br>');
      }
      // 状态栏也显示一个外部地址
      if (lanUrls.length > 0) {
        const statusMsg = '就绪 · 局域网可访问: ' + lanUrls[0];
        setStatus(statusMsg, '');
      }
    } catch (e) {
      console.warn('获取服务器信息失败:', e);
    }
  }

  function startClock() {
    const el = document.getElementById('clock');
    if (!el) return;
    function tick() {
      const d = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      el.textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    }
    tick();
    setInterval(tick, 1000);
  }

  // ========================= 驱动器 =========================
  async function loadDrives() {
    try {
      const res = await fetch('/api/drives');
      const drives = await res.json();
      STATE.drives = drives;

      // 填充下拉框
      const sel = document.getElementById('driveSelect');
      sel.innerHTML = '';
      drives.forEach((d) => {
        const opt = document.createElement('option');
        opt.value = d.mountpoint;
        opt.textContent = `${d.device} (${d.mountpoint})  [${d.fstype}]  ${d.used_str}/${d.total_str} (${d.percent}%)`;
        sel.appendChild(opt);
      });

      // 填充左侧摘要
      const summary = document.getElementById('driveSummary');
      summary.innerHTML = '';
      drives.forEach((d) => {
        const item = document.createElement('div');
        item.className = 'drive-item';
        item.dataset.mountpoint = d.mountpoint;
        let barClass = '';
        if (d.percent > 85) barClass = 'danger';
        else if (d.percent > 70) barClass = 'warn';
        item.innerHTML = `
          <div class="drive-header">
            <span>💿 ${escapeHtml(d.device)}</span>
            <span class="drive-size-text">${d.percent}%</span>
          </div>
          <div class="drive-bar-container">
            <div class="drive-bar-fill ${barClass}" style="width: ${Math.min(100, d.percent)}%"></div>
          </div>
          <div class="drive-meta">
            <span>已用 ${escapeHtml(d.used_str)}</span>
            <span>共 ${escapeHtml(d.total_str)}</span>
          </div>
        `;
        item.addEventListener('click', () => {
          document.querySelectorAll('.drive-item').forEach((i) => i.classList.remove('active'));
          item.classList.add('active');
          document.getElementById('driveSelect').value = d.mountpoint;
          scanPath(d.mountpoint);
        });
        summary.appendChild(item);
      });
    } catch (e) {
      console.error('加载驱动器失败:', e);
      document.getElementById('driveSummary').innerHTML =
        '<div class="empty-small">加载失败</div>';
    }
  }

  // ========================= 扫描 =========================
  async function scanPath(path) {
    if (!path || !path.trim()) return;
    path = path.trim();

    STATE.currentPath = path;
    STATE.rootPath = path;
    document.getElementById('pathInput').value = path;

    // 显示进度条
    document.getElementById('progressBar').style.display = 'flex';
    document.getElementById('progressBarFill').style.width = '0%';
    document.getElementById('progressText').textContent = '扫描中...';

    setStatus(`正在扫描: ${path}`, 'scanning');
    // 清空列表/树/图表
    document.getElementById('treeView').innerHTML = '<div class="empty-state"><div class="empty-icon">⏳</div><p>正在扫描...</p></div>';
    document.getElementById('listBody').innerHTML = '<div class="empty-state"><div class="empty-icon">⏳</div><p>正在读取目录内容...</p></div>';
    STATE.chartInstance.clear();

    try {
      const res = await fetch('/api/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, max_depth: 99 }),
      });
      const data = await res.json();
      STATE.scanId = data.scan_id;

      // 等待后端扫描完成
      await waitScanDone(STATE.scanId);

      // 加载列表 & 树 & 图表
      await Promise.all([
        loadList(path),
        loadTree(path),
        loadChart(path, STATE.view),
      ]);

      setStatus(`扫描完成: ${path}`, '');
    } catch (e) {
      console.error('扫描失败:', e);
      setStatus(`扫描失败: ${e.message}`, 'error');
    } finally {
      document.getElementById('progressBar').style.display = 'none';
    }
  }

  function waitScanDone(scanId) {
    return new Promise((resolve) => {
      const startTime = Date.now();
      function poll() {
        fetch(`/api/scan/progress/${scanId}`)
          .then((r) => r.json())
          .then((p) => {
            const fill = document.getElementById('progressBarFill');
            const txt = document.getElementById('progressText');
            const pct = Math.min(99, p.current || 0);
            if (fill) fill.style.width = pct + '%';
            if (txt) txt.textContent = `扫描 ${pct}%`;
            setStatus(`正在扫描: ${p.current_item || path}`, 'scanning');
            if (p.done) {
              resolve();
            } else if (Date.now() - startTime > 60000) {
              resolve();
            } else {
              setTimeout(poll, 800);
            }
          })
          .catch(() => {
            setTimeout(poll, 1000);
          });
      }
      poll();
    });
  }

  // ========================= 目录树 =========================
  async function loadTree(rootPath) {
    // 根节点
    const treeView = document.getElementById('treeView');
    treeView.innerHTML = '';
    const rootNode = createTreeNode(rootPath, 0, true);
    treeView.appendChild(rootNode);

    // 异步获取根目录第一层子文件夹，用于可展开标识
    try {
      const listRes = await fetch(
        `/api/node/list?path=${encodeURIComponent(rootPath)}&sort_by=size&sort_order=desc`
      );
      const listData = await listRes.json();
      const children = (listData.items || []).filter((i) => i.is_dir);
      if (children.length > 0) {
        rootNode.dataset.hasChildren = '1';
        const toggle = rootNode.querySelector('.tree-toggle');
        toggle.textContent = '▼';
        toggle.classList.remove('empty');
        // 展开第一级
        expandTreeNode(rootNode, rootPath, 0);
      } else {
        rootNode.querySelector('.tree-toggle').textContent = '○';
        rootNode.querySelector('.tree-toggle').classList.add('empty');
      }
    } catch (e) {
      console.error('加载树失败:', e);
    }
  }

  function createTreeNode(path, depth, isRoot) {
    const node = document.createElement('div');
    node.className = 'tree-node';
    node.dataset.path = path;
    node.dataset.depth = depth;
    node.style.paddingLeft = (4 + depth * 14) + 'px';
    const name = isRoot ? path : path.split(/[\\/]/).filter(Boolean).pop() || path;

    node.innerHTML = `
      <span class="tree-toggle">▶</span>
      <span class="tree-icon">${isRoot ? '💿' : '📁'}</span>
      <span class="tree-name" title="${escapeHtml(path)}">${escapeHtml(name)}</span>
    `;

    // 点击选中
    node.addEventListener('click', (e) => {
      if (e.target.classList.contains('tree-toggle')) return;
      document.querySelectorAll('.tree-node.selected').forEach((n) => n.classList.remove('selected'));
      node.classList.add('selected');
      STATE.currentPath = path;
      loadList(path);
      loadChart(path, STATE.view);
      updateBreadcrumb(path);
    });

    // 点击展开/折叠
    const toggle = node.querySelector('.tree-toggle');
    toggle.addEventListener('click', (e) => {
      e.stopPropagation();
      if (toggle.classList.contains('empty')) return;
      if (toggle.textContent === '▼') {
        // 折叠: 移除之后的所有深度大于当前的节点
        toggle.textContent = '▶';
        let sib = node.nextSibling;
        while (sib && sib.dataset && parseInt(sib.dataset.depth) > depth) {
          const next = sib.nextSibling;
          sib.remove();
          sib = next;
        }
      } else {
        expandTreeNode(node, path, depth);
      }
    });

    // 右键菜单
    node.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      STATE.currentContextPath = path;
      STATE.currentContextName = name;
      showContextMenu(e.clientX, e.clientY);
    });

    return node;
  }

  async function expandTreeNode(node, path, depth) {
    const toggle = node.querySelector('.tree-toggle');
    // 清理已存在的子节点
    let sib = node.nextSibling;
    while (sib && sib.dataset && parseInt(sib.dataset.depth) > depth) {
      const next = sib.nextSibling;
      sib.remove();
      sib = next;
    }

    try {
      const res = await fetch(`/api/node/list?path=${encodeURIComponent(path)}&sort_by=size&sort_order=desc`);
      const data = await res.json();
      const children = (data.items || []).filter((i) => i.is_dir);
      if (children.length === 0) {
        toggle.textContent = '○';
        toggle.classList.add('empty');
        return;
      }
      toggle.textContent = '▼';

      const frag = document.createDocumentFragment();
      // 显示大小（从当前节点计算）
      const parentSize = data.items.reduce((s, i) => s + i.size, 0) || 1;
      for (const child of children) {
        const childNode = createTreeNode(child.path, depth + 1, false);
        // 添加大小信息
        const sizeEl = document.createElement('span');
        sizeEl.className = 'tree-size-text';
        sizeEl.textContent = formatSize(child.size);
        childNode.appendChild(sizeEl);

        const bar = document.createElement('span');
        bar.className = 'tree-bar-mini';
        const pct = Math.max(1, (child.size / parentSize) * 100);
        bar.innerHTML = `<span class="tree-bar-mini-fill" style="width:${Math.min(100, pct)}%"></span>`;
        childNode.appendChild(bar);

        frag.appendChild(childNode);
      }
      node.after(frag);
    } catch (e) {
      toggle.textContent = '▶';
    }
  }

  function updateBreadcrumb(path) {
    const el = document.getElementById('breadcrumb');
    const chartPath = document.getElementById('chartPath');
    if (el) el.textContent = path.length > 50 ? '...' + path.slice(-50) : path;
    if (chartPath) chartPath.textContent = path.length > 40 ? '...' + path.slice(-40) : path;
  }

  // ========================= 文件列表 =========================
  async function loadList(path) {
    if (!path) return;
    updateBreadcrumb(path);

    const listBody = document.getElementById('listBody');
    listBody.innerHTML = '<div class="empty-state"><div class="empty-icon">⏳</div><p>加载中...</p></div>';

    let url = `/api/node/list?path=${encodeURIComponent(path)}&sort_by=${STATE.sortBy}&sort_order=${STATE.sortOrder}`;
    if (STATE.filterText) url += `&filter=${encodeURIComponent(STATE.filterText)}`;
    if (STATE.extFilter) url += `&ext=${encodeURIComponent(STATE.extFilter)}`;

    try {
      const res = await fetch(url);
      const data = await res.json();
      STATE.currentItems = data.items || [];
      document.getElementById('listSummary').textContent = `${data.items.length} 项`;
      document.getElementById('treeBadge').textContent = `${data.items.length} 项`;

      renderListItems();
    } catch (e) {
      console.error('加载列表失败:', e);
      listBody.innerHTML = '<div class="empty-state"><div class="empty-icon">❌</div><p>加载失败</p></div>';
    }
  }

  function renderListItems() {
    const listBody = document.getElementById('listBody');
    const items = STATE.currentItems;

    if (!items || items.length === 0) {
      listBody.innerHTML = '<div class="empty-state"><div class="empty-icon">📂</div><p>此目录为空</p></div>';
      return;
    }

    const totalSize = items.reduce((s, i) => s + i.size, 0) || 1;

    const frag = document.createDocumentFragment();
    for (const item of items) {
      const row = document.createElement('div');
      row.className = 'list-row';
      row.dataset.path = item.path;
      row.dataset.isDir = item.is_dir;

      const pct = Math.round((item.size / totalSize) * 100);
      const pctDisplay = Math.max(1, pct);

      row.innerHTML = `
        <div class="col col-icon">${getFileIcon(item.name, item.is_dir)}</div>
        <div class="col col-name" title="${escapeHtml(item.path)}">${escapeHtml(item.name)}</div>
        <div class="col col-size"><span class="size-text-right">${formatSize(item.size)}</span></div>
        <div class="col col-pct">
          <div class="size-bar-wrapper">
            <span class="size-bar-track">
              <span class="size-bar-fill ${getPctColor(pct)}" style="width:${pctDisplay}%"></span>
            </span>
            <span class="size-bar-value">${pct}%</span>
          </div>
        </div>
        <div class="col col-allocated">${formatSize(item.allocated || item.size)}</div>
        <div class="col col-files">${item.is_dir && item.files > 0 ? item.files.toLocaleString() : (item.is_dir ? '0' : '-')}</div>
        <div class="col col-folders">${item.is_dir && item.folders > 0 ? item.folders.toLocaleString() : '-'}</div>
        <div class="col col-modified">${escapeHtml(item.modified || '-')}</div>
      `;

      // 点击
      row.addEventListener('click', () => {
        document.querySelectorAll('.list-row.selected').forEach((r) => r.classList.remove('selected'));
        row.classList.add('selected');
        // 高亮树中的匹配节点（如果已存在）
        const existingNode = document.querySelector(`.tree-node[data-path="${CSS.escape(item.path)}"]`);
        if (existingNode) {
          document.querySelectorAll('.tree-node.selected').forEach((n) => n.classList.remove('selected'));
          existingNode.classList.add('selected');
        }
        STATE.currentContextPath = item.path;
        STATE.currentContextName = item.name;
      });

      // 双击进入目录
      row.addEventListener('dblclick', () => {
        if (item.is_dir) {
          STATE.currentPath = item.path;
          loadList(item.path);
          loadChart(item.path, STATE.view);
          updateBreadcrumb(item.path);
          // 同时展开树节点
          let treeNode = document.querySelector(`.tree-node[data-path="${CSS.escape(item.path)}"]`);
          if (!treeNode) {
            // 动态在已展开的父节点下查找/新增
            const parentPath = item.path.slice(0, -item.name.length - 1);
            const parentNode = document.querySelector(`.tree-node[data-path="${CSS.escape(parentPath)}"]`);
            if (parentNode) {
              const toggle = parentNode.querySelector('.tree-toggle');
              if (toggle.textContent === '▶') {
                const depth = parseInt(parentNode.dataset.depth);
                expandTreeNode(parentNode, parentPath, depth);
              }
            }
          }
        }
      });

      // 右键菜单
      row.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        STATE.currentContextPath = item.path;
        STATE.currentContextName = item.name;
        showContextMenu(e.clientX, e.clientY);
      });

      frag.appendChild(row);
    }

    listBody.innerHTML = '';
    listBody.appendChild(frag);
  }

  // ========================= 排序处理 =========================
  function initSortHeaders() {
    document.querySelectorAll('.list-header .sortable').forEach((col) => {
      col.addEventListener('click', () => {
        const newSortBy = col.dataset.sort;
        if (STATE.sortBy === newSortBy) {
          STATE.sortOrder = STATE.sortOrder === 'desc' ? 'asc' : 'desc';
        } else {
          STATE.sortBy = newSortBy;
          STATE.sortOrder = 'desc';
        }
        // 更新图标
        document.querySelectorAll('.list-header .sortable').forEach((c) => {
          c.classList.remove('sorted-desc', 'sorted-asc');
        });
        col.classList.add(STATE.sortOrder === 'desc' ? 'sorted-desc' : 'sorted-asc');
        loadList(STATE.currentPath);
      });
    });
  }

  // ========================= 图表 =========================
  function initChart() {
    try {
      STATE.chartInstance = echarts.init(document.getElementById('chartContainer'));
      window.addEventListener('resize', () => {
        if (STATE.chartInstance) STATE.chartInstance.resize();
      });
    } catch (e) {
      console.error('图表初始化失败:', e);
    }
  }

  async function loadChart(path, view) {
    if (!STATE.chartInstance || !path) return;
    STATE.view = view;

    // 更新按钮
    document.querySelectorAll('.view-switch .btn').forEach((b) => b.classList.remove('active-view'));
    const btn = document.querySelector(`.view-switch .btn[data-view="${view}"]`);
    if (btn) btn.classList.add('active-view');

    document.getElementById('chartTitle').textContent = {
      details: '📋 详情视图',
      treemap: '▣ 矩形树状图',
      pie: '◔ 文件类型饼图',
      bar: '▦ 最大文件夹柱状图',
      topfiles: '📄 最大文件列表',
      duplicates: '♊ 重复文件检测',
      old: '📅 老旧文件',
    }[view] || '可视化';

    document.getElementById('chartLegend').textContent = `正在加载 ${view} 数据...`;

    try {
      if (view === 'treemap') await renderTreemap(path);
      else if (view === 'pie') await renderPieChart(path);
      else if (view === 'bar') await renderBarChart(path);
      else if (view === 'topfiles') await renderTopFilesChart(path);
      else if (view === 'duplicates') await renderDuplicatesChart(path);
      else if (view === 'old') await renderOldFilesChart(path);
      else await renderTreemap(path);
      STATE.chartInstance.resize();
    } catch (e) {
      console.error('图表渲染失败:', e);
      document.getElementById('chartLegend').textContent = '暂无数据';
    }
  }

  async function renderTreemap(path) {
    const res = await fetch(`/api/viz/treemap?path=${encodeURIComponent(path)}&depth=2`);
    const data = await res.json();

    if (!data || !data.length) {
      STATE.chartInstance.clear();
      document.getElementById('chartLegend').textContent = '此目录下没有可展示的子项';
      return;
    }

    const colors = ['#1976d2', '#43a047', '#fb8c00', '#e53935', '#7b1fa2', '#00838f', '#5d4037',
                    '#00897b', '#8e24aa', '#ef6c00', '#2e7d32', '#ad1457', '#1565c0', '#455a64',
                    '#6d4c41', '#558b2f', '#283593', '#c62828', '#00695c'];

    function build(entries, idx = 0, totalForParent = null) {
      const total = totalForParent || entries.reduce((s, e) => s + (e.value || 0), 0);
      return entries.map((e, i) => {
        const item = {
          name: e.name + ' (' + formatSize(e.value || 0) + ')',
          value: e.value || 0,
          itemStyle: { color: colors[(idx + i) % colors.length] },
        };
        if (e.children && e.children.length) {
          item.children = build(e.children, (idx + i) * 3, total);
        }
        return item;
      });
    }

    const option = {
      tooltip: {
        formatter: (params) => {
          return `<b>${escapeHtml(params.name)}</b><br/>大小: ${formatSize(params.value || 0)}`;
        },
      },
      series: [{
        type: 'treemap',
        roam: true,
        data: build(data),
        breadcrumb: { show: false },
        label: {
          show: true,
          formatter: (p) => {
            if (!p.name) return '';
            const display = p.name.replace(/\s*\([^)]*\)$/, '');
            return display.length > 16 ? display.slice(0, 14) + '..' : display;
          },
          fontSize: 10,
          color: '#fff',
          textShadowColor: 'rgba(0,0,0,0.4)',
          textShadowBlur: 2,
        },
        upperLabel: { show: false },
        levels: [
          { colorMappingBy: 'value', itemStyle: { borderColor: '#fff', borderWidth: 2, gapWidth: 2 } },
          { itemStyle: { borderColor: '#e0e0e0', borderWidth: 1 } },
        ],
      }],
    };

    STATE.chartInstance.setOption(option, true);
    document.getElementById('chartLegend').textContent = `共 ${data.length} 个主要项目 (方块大小对应占用空间)`;
  }

  async function renderPieChart(path) {
    const res = await fetch(`/api/viz/pie-ext?path=${encodeURIComponent(path)}&depth=3&limit=12`);
    const data = await res.json();

    if (!data.data || !data.data.length) {
      STATE.chartInstance.clear();
      document.getElementById('chartLegend').textContent = '暂无数据';
      return;
    }

    const option = {
      tooltip: {
        trigger: 'item',
        formatter: (p) => `<b>${escapeHtml(p.name)}</b><br/>大小: ${formatSize(p.value)}<br/>占比: ${p.percent}%<br/>文件数: ${p.data.count || '-'}`,
      },
      legend: {
        orient: 'vertical',
        right: '2%',
        top: 'center',
        textStyle: { fontSize: 11 },
        formatter: (n) => (n.length > 20 ? n.slice(0, 18) + '..' : n),
      },
      series: [{
        name: '文件类型',
        type: 'pie',
        radius: ['35%', '68%'],
        center: ['40%', '50%'],
        itemStyle: { borderRadius: 3, borderColor: '#fff', borderWidth: 2 },
        label: {
          show: true,
          formatter: (p) => {
            const name = p.name.length > 10 ? p.name.slice(0, 9) + '..' : p.name;
            return `${name}\n${p.percent}%`;
          },
          fontSize: 10,
        },
        emphasis: {
          label: { show: true, fontSize: 12, fontWeight: 'bold' },
          itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.3)' },
        },
        data: data.data.map((d) => ({
          name: d.name,
          value: d.value,
          count: d.count,
        })),
      }],
    };

    STATE.chartInstance.setOption(option, true);
    document.getElementById('chartLegend').textContent = `总大小: ${data.total} · 共 ${data.data.length} 类文件`;
  }

  async function renderBarChart(path) {
    const res = await fetch(`/api/viz/top-folders?path=${encodeURIComponent(path)}&limit=15`);
    const data = await res.json();

    if (!data || !data.length) {
      STATE.chartInstance.clear();
      document.getElementById('chartLegend').textContent = '此目录下没有子文件夹';
      return;
    }

    const option = {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params) => {
          const p = params[0];
          const fcount = p.data.files || 0;
          return `<b>${escapeHtml(p.name)}</b><br/>大小: ${formatSize(p.value)}<br/>文件数: ${fcount.toLocaleString()}`;
        },
      },
      grid: { left: '3%', right: '8%', bottom: '3%', top: '3%', containLabel: true },
      xAxis: { type: 'value', axisLabel: { formatter: (v) => formatSize(v), fontSize: 10 } },
      yAxis: {
        type: 'category',
        data: data.map((d) => (d.name.length > 22 ? d.name.slice(0, 20) + '..' : d.name)).reverse(),
        axisLabel: { fontSize: 10 },
        inverse: false,
      },
      series: [{
        type: 'bar',
        data: data.map((d) => ({
          value: d.value,
          name: d.name,
          files: d.files,
          itemStyle: {
            color: d.value > 1024 * 1024 * 1024 ? '#e53935' : (d.value > 1024 * 1024 * 100 ? '#fb8c00' : '#1976d2'),
            borderRadius: [0, 3, 3, 0],
          },
        })).reverse(),
        label: {
          show: true,
          position: 'right',
          formatter: (p) => formatSize(p.value),
          fontSize: 10,
        },
        barMaxWidth: 22,
      }],
    };

    STATE.chartInstance.setOption(option, true);
    document.getElementById('chartLegend').textContent = `显示 ${data.length} 个最大文件夹`;
  }

  async function renderTopFilesChart(path) {
    const res = await fetch(`/api/viz/top-files?path=${encodeURIComponent(path)}&limit=20`);
    const data = await res.json();

    if (!data || !data.length) {
      STATE.chartInstance.clear();
      document.getElementById('chartLegend').textContent = '此目录下没有大文件';
      return;
    }

    const option = {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params) => {
          const p = params[0];
          return `<b>${escapeHtml(p.name)}</b><br/>大小: ${formatSize(p.value)}<br/>路径: ${escapeHtml((p.data.path || '').slice(-50))}`;
        },
      },
      grid: { left: '3%', right: '8%', bottom: '10%', top: '3%', containLabel: true },
      xAxis: {
        type: 'category',
        data: data.map((d) => (d.name.length > 18 ? d.name.slice(0, 16) + '..' : d.name)),
        axisLabel: { rotate: 45, fontSize: 10 },
      },
      yAxis: { type: 'value', axisLabel: { formatter: (v) => formatSize(v), fontSize: 10 } },
      series: [{
        type: 'bar',
        data: data.map((d) => ({
          value: d.value,
          name: d.name,
          path: d.path,
          itemStyle: {
            color: d.value > 1024 * 1024 * 1024 ? '#c62828' : (d.value > 1024 * 1024 * 100 ? '#ef6c00' : '#3949ab'),
            borderRadius: [4, 4, 0, 0],
          },
        })),
        label: { show: true, position: 'top', formatter: (p) => formatSize(p.value), fontSize: 10 },
        barMaxWidth: 30,
      }],
    };

    STATE.chartInstance.setOption(option, true);
    document.getElementById('chartLegend').textContent = `最大的 ${data.length} 个文件 (点击路径可查看详细)`;
  }

  async function renderDuplicatesChart(path) {
    document.getElementById('chartLegend').textContent = '正在检测重复文件（基于大小+哈希）...';
    const res = await fetch(`/api/search/duplicates?path=${encodeURIComponent(path)}&limit=50`);
    const data = await res.json();

    if (!data || !data.length) {
      STATE.chartInstance.clear();
      document.getElementById('chartLegend').textContent = '未发现重复文件';
      return;
    }

    // 以表格+柱状图方式展示
    const topGroups = data.slice(0, 20);
    const option = {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params) => {
          const p = params[0];
          return `<b>哈希: ${escapeHtml(String(p.data.hash || '').slice(0, 16))}...</b><br/>
                  每份大小: ${formatSize(p.data.size || 0)}<br/>
                  重复数: ${p.data.count} 个<br/>
                  可节省: ${formatSize(p.data.wasted_bytes || 0)}`;
        },
      },
      grid: { left: '3%', right: '8%', bottom: '3%', top: '3%', containLabel: true },
      xAxis: { type: 'value', axisLabel: { formatter: (v) => formatSize(v), fontSize: 10 } },
      yAxis: {
        type: 'category',
        data: topGroups.map((d, i) => `#${i + 1} (${d.count}个)`),
        axisLabel: { fontSize: 10 },
        inverse: true,
      },
      series: [{
        type: 'bar',
        data: topGroups.map((d) => ({
          value: d.wasted_bytes,
          size: d.size,
          count: d.count,
          hash: d.hash,
          itemStyle: { color: '#8e24aa', borderRadius: [0, 3, 3, 0] },
        })),
        label: { show: true, position: 'right', formatter: (p) => '可节省: ' + formatSize(p.value), fontSize: 10 },
        barMaxWidth: 20,
      }],
    };

    STATE.chartInstance.setOption(option, true);

    // 下方文字列表
    let html = `<b>共 ${data.length} 组重复文件</b> · 可节省: <b style="color:#e53935">${formatSize(
      data.reduce((s, d) => s + d.wasted_bytes, 0)
    )}</b>`;
    document.getElementById('chartLegend').innerHTML = html;
  }

  async function renderOldFilesChart(path) {
    document.getElementById('chartLegend').textContent = '正在检测长期未修改文件...';
    const res = await fetch(`/api/search/old-files?path=${encodeURIComponent(path)}&days=365&limit=30`);
    const data = await res.json();

    if (!data || !data.length) {
      STATE.chartInstance.clear();
      document.getElementById('chartLegend').textContent = '未发现长期未修改的文件';
      return;
    }

    const option = {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params) => {
          const p = params[0];
          return `<b>${escapeHtml(p.data.name)}</b><br/>大小: ${formatSize(p.value)}<br/>
                  上次修改: ${escapeHtml(p.data.modified || '-')}<br/>
                  已闲置: ${p.data.days_old || 0} 天`;
        },
      },
      grid: { left: '3%', right: '8%', bottom: '10%', top: '3%', containLabel: true },
      xAxis: {
        type: 'category',
        data: data.slice(0, 20).map((d) => (d.name.length > 18 ? d.name.slice(0, 16) + '..' : d.name)),
        axisLabel: { rotate: 45, fontSize: 10 },
      },
      yAxis: { type: 'value', axisLabel: { formatter: (v) => formatSize(v), fontSize: 10 } },
      series: [{
        type: 'bar',
        data: data.slice(0, 20).map((d) => ({
          value: d.size,
          name: d.name,
          modified: d.modified,
          days_old: d.days_old,
          itemStyle: {
            color: '#6d4c41',
            borderRadius: [4, 4, 0, 0],
          },
        })),
        label: { show: true, position: 'top', formatter: (p) => formatSize(p.value), fontSize: 10 },
        barMaxWidth: 28,
      }],
    };

    STATE.chartInstance.setOption(option, true);

    const totalSize = data.reduce((s, d) => s + d.size, 0);
    document.getElementById('chartLegend').textContent = `发现 ${data.length} 个长期未修改文件 · 可清理: ${formatSize(totalSize)}`;
  }

  // ========================= 右键菜单 =========================
  function showContextMenu(x, y) {
    const menu = document.getElementById('contextMenu');
    menu.style.display = 'block';
    menu.style.left = Math.min(x, window.innerWidth - 220) + 'px';
    menu.style.top = Math.min(y, window.innerHeight - 200) + 'px';
  }

  function hideContextMenu() {
    document.getElementById('contextMenu').style.display = 'none';
  }

  // ========================= 事件绑定 =========================
  function bindEvents() {
    // 扫描按钮
    document.getElementById('btnScan').addEventListener('click', () => {
      const input = document.getElementById('pathInput');
      scanPath(input.value.trim() || document.getElementById('driveSelect').value);
    });

    // 刷新按钮
    document.getElementById('btnRefresh').addEventListener('click', () => {
      if (STATE.currentPath) {
        loadList(STATE.currentPath);
        loadChart(STATE.currentPath, STATE.view);
        setStatus('已刷新: ' + STATE.currentPath, '');
      }
    });

    // 驱动器切换
    document.getElementById('driveSelect').addEventListener('change', (e) => {
      scanPath(e.target.value);
    });

    // 路径输入框 Enter
    document.getElementById('pathInput').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        scanPath(e.target.value.trim());
      }
    });

    // 视图切换按钮
    document.querySelectorAll('.view-switch .btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const view = btn.dataset.view;
        document.querySelectorAll('.view-switch .btn').forEach((b) => b.classList.remove('active-view'));
        btn.classList.add('active-view');
        STATE.view = view;
        loadChart(STATE.currentPath || STATE.rootPath, view);
      });
    });

    // 过滤
    document.getElementById('filterInput').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        STATE.filterText = e.target.value.trim();
        loadList(STATE.currentPath);
      }
    });
    document.getElementById('extFilter').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        STATE.extFilter = e.target.value.trim();
        loadList(STATE.currentPath);
      }
    });

    // 导出菜单
    const exportBtn = document.getElementById('btnExport');
    const exportMenu = document.getElementById('exportMenu');
    exportBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      exportMenu.classList.toggle('show');
    });
    document.querySelectorAll('.export-option').forEach((opt) => {
      opt.addEventListener('click', () => {
        const fmt = opt.dataset.format;
        const path = STATE.currentPath || STATE.rootPath;
        if (!path) return;
        window.open(`/api/export?path=${encodeURIComponent(path)}&format=${fmt}`, '_blank');
        exportMenu.classList.remove('show');
      });
    });

    // 关闭下拉菜单
    document.addEventListener('click', (e) => {
      if (!e.target.closest('.export-container')) {
        exportMenu.classList.remove('show');
      }
    });

    // 关于
    document.getElementById('btnAbout').addEventListener('click', () => {
      document.getElementById('aboutModal').style.display = 'flex';
    });
    document.getElementById('aboutClose').addEventListener('click', hideAboutModal);
    document.getElementById('aboutOk').addEventListener('click', hideAboutModal);
    document.getElementById('aboutModal').addEventListener('click', (e) => {
      if (e.target.id === 'aboutModal') hideAboutModal();
    });

    // 服务器信息对话框
    document.getElementById('btnServer').addEventListener('click', () => {
      document.getElementById('serverModal').style.display = 'flex';
    });
    document.getElementById('serverClose').addEventListener('click', hideServerModal);
    document.getElementById('serverOk').addEventListener('click', hideServerModal);
    document.getElementById('serverModal').addEventListener('click', (e) => {
      if (e.target.id === 'serverModal') hideServerModal();
    });

    function hideServerModal() {
      document.getElementById('serverModal').style.display = 'none';
    }

    // 右键菜单全局关闭
    document.addEventListener('click', (e) => {
      if (!e.target.closest('.context-menu')) hideContextMenu();
    });
    document.querySelectorAll('.context-menu .cm-item').forEach((item) => {
      item.addEventListener('click', () => {
        const action = item.dataset.action;
        const path = STATE.currentContextPath;
        if (!path) return;
        if (action === 'open') {
          setStatus(`打开: ${path}`, '');
        } else if (action === 'copy-path') {
          navigator.clipboard?.writeText(path);
          setStatus('已复制路径: ' + path, '');
        } else if (action === 'copy-size') {
          navigator.clipboard?.writeText(formatSize(STATE.currentItems.find((i) => i.path === path)?.size || 0));
          setStatus('已复制大小信息', '');
        } else if (action === 'scan') {
          scanPath(path);
        } else if (action === 'set-root') {
          STATE.rootPath = path;
          STATE.currentPath = path;
          scanPath(path);
        }
        hideContextMenu();
      });
    });
    document.addEventListener('contextmenu', (e) => {
      // 在空白区域的右键不阻止默认，已由具体节点处理
    });

    // 初始化排序头
    initSortHeaders();

    // ESC 关闭对话框
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        hideAboutModal();
        document.getElementById('serverModal').style.display = 'none';
        hideContextMenu();
        document.getElementById('exportMenu').classList.remove('show');
      }
    });
  }

  function hideAboutModal() {
    document.getElementById('aboutModal').style.display = 'none';
  }

  // ========================= 启动 =========================
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
