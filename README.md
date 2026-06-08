# OppenDiskAnalysis (ODA)

> 📊 开源磁盘空间分析软件

一个基于 Web 的磁盘空间可视化与分析工具。

## ✨ 功能特性

- **📁 目录树浏览** — 按大小递归排序显示所有目录
- **▣ 矩形树状图 (Treemap)** — 直观的方块可视化，大小对应磁盘占用
- **◔ 文件类型统计** — 按扩展名分组的饼图统计
- **📊 最大文件夹柱状图** — Top N 大文件夹排名
- **📄 大文件搜索** — 快速定位占用空间最大的文件
- **♊ 重复文件检测** — 基于大小+哈希的重复文件识别
- **📅 老旧文件分析** — 查找长期未修改的文件
- **🔍 实时过滤** — 按文件名、扩展名筛选
- **📤 导出报告** — 支持 CSV / HTML 格式导出

## 🚀 快速开始

### 环境要求

- Python 3.8+
- Flask
- psutil

### 安装依赖

```bash
pip install flask psutil
```

### 启动应用

```bash
cd oppendiskanalysis
python app.py
```

然后在浏览器中打开: **http://127.0.0.1:5199**

## 📂 项目结构

```
oppendiskanalysis/
├── app.py              # Flask 后端核心 (扫描引擎 + API)
├── templates/
│   └── index.html      # 前端主界面
├── static/
│   ├── css/style.css   # 桌面应用风格样式
│   └── js/app.js       # 前端交互与 ECharts 图表
└── README.md
```

## 🔧 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python + Flask |
| 前端 | 原生 HTML5 + CSS3 + JavaScript |
| 图表 | Apache ECharts |
| 系统信息 | psutil |

## 📡 API 接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/drives` | GET | 获取所有磁盘分区 |
| `/api/scan` | POST | 启动目录扫描 |
| `/api/scan/progress/<id>` | GET | 获取扫描进度 |
| `/api/node/list` | GET | 获取目录内容列表 |
| `/api/viz/treemap` | GET | 树状图数据 |
| `/api/viz/pie-ext` | GET | 文件类型饼图数据 |
| `/api/viz/top-folders` | GET | 最大文件夹数据 |
| `/api/viz/top-files` | GET | 最大文件数据 |
| `/api/search/large-files` | GET | 大文件搜索 |
| `/api/search/old-files` | GET | 老旧文件搜索 |
| `/api/search/duplicates` | GET | 重复文件检测 |
| `/api/summary` | GET | 目录摘要信息 |
| `/api/export` | GET | CSV/HTML 导出 |

## 🖼️ 界面预览

**三栏布局** :
- **左栏**: 驱动器摘要 + 可展开目录树
- **中栏**: 详细文件列表（大小、百分比、文件数、修改时间）
- **右栏**: 可视化图表切换区 (树状图/饼图/柱状图)

## 📝 说明

本项目为开源 Web 实现参考版本，适合学习与二次开发。

## 📄 License

AGPL-3.0 license
