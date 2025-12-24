import os
import time
import json
import html as _html


def format_size(size):
    """格式化文件大小"""
    try:
        size = float(size)
    except Exception:
        size = 0.0

    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def _esc(s):
    """HTML escape（防止路径/文件名中的特殊字符破坏页面）"""
    return _html.escape(str(s), quote=True)


class EnhancedHTMLReporter:
    def __init__(self, scan_data):
        """
        初始化报告生成器
        :param scan_data: 包含所有扫描信息的字典
        """
        self.data = scan_data or {}
        self.current_time = time.strftime('%Y-%m-%d %H:%M:%S')

        # 兼容不同版本 analyzer 输出：归一化关键字段，避免 KeyError/类型错误
        self.disk_usage_percent = self._coerce_disk_usage_percent(self.data.get('disk_usage', 0))
        self.data['disk_usage_percent'] = self.disk_usage_percent

        # file_types: 允许 dict 或 [{'ext':..., 'size':...}, ...]
        self.data['file_types'] = self._coerce_file_types(self.data.get('file_types', {}))

        # history_data: 允许缺字段，保证每条至少有 date/size/usage
        self.data['history_data'] = self._coerce_history(self.data.get('history_data', []))

        # duplicate_files: 允许多种结构，统一为 [ [ {path,size,mtime}, ... ], ... ]
        self.data['duplicate_files'] = self._coerce_duplicates(self.data.get('duplicate_files', []))

    def _coerce_disk_usage_percent(self, disk_usage):
        """disk_usage 可能是 dict(含 used_percent) 或数字；统一成 float 百分比"""
        try:
            if isinstance(disk_usage, dict):
                for k in ('used_percent', 'usage', 'percent'):
                    if k in disk_usage:
                        return float(disk_usage.get(k) or 0)
                if 'used' in disk_usage and 'total' in disk_usage and disk_usage.get('total'):
                    return float(disk_usage['used']) / float(disk_usage['total']) * 100.0
                return 0.0
            return float(disk_usage)
        except Exception:
            return 0.0

    def _coerce_file_types(self, file_types):
        """file_types 兼容 dict 或 list[{'ext','size'}]"""
        if isinstance(file_types, dict):
            return file_types
        if isinstance(file_types, list):
            out = {}
            for item in file_types:
                if isinstance(item, dict):
                    ext = item.get('ext')
                    size = item.get('size', 0)
                    if ext is None:
                        continue
                    out[str(ext)] = out.get(str(ext), 0) + (size or 0)
            return out
        return {}

    def _coerce_history(self, history):
        """确保 history 每条都有 date/size/usage。size=bytes，usage=百分比"""
        if not isinstance(history, list) or not history:
            return history if isinstance(history, list) else []

        out = []
        for i, item in enumerate(history):
            if not isinstance(item, dict):
                continue
            date = item.get('date') or item.get('time') or item.get('day')
            size = item.get('size')
            usage = item.get('usage')

            if size is None:
                if 'used_bytes' in item:
                    size = item.get('used_bytes')
                elif 'used' in item and isinstance(item.get('used'), (int, float)):
                    size = item.get('used')

            if usage is None:
                if 'used_percent' in item:
                    usage = item.get('used_percent')

            if date is None:
                date = str(i)
            if size is None:
                size = 0
            if usage is None:
                total = None
                du = self.data.get('disk_usage')
                if isinstance(du, dict):
                    total = du.get('total')
                if total:
                    try:
                        usage = float(size) / float(total) * 100.0
                    except Exception:
                        usage = self.disk_usage_percent
                else:
                    usage = self.disk_usage_percent

            try:
                size = float(size)
            except Exception:
                size = 0.0
            try:
                usage = float(usage)
            except Exception:
                usage = self.disk_usage_percent

            out.append({'date': date, 'size': size, 'usage': usage})
        return out

    def _coerce_duplicates(self, duplicates):
        """统一 duplicate_files 为 list[list[dict]]"""
        if duplicates is None:
            return []

        if isinstance(duplicates, list):
            if not duplicates:
                return []
            if isinstance(duplicates[0], dict):
                groups = []
                for d in duplicates:
                    if not isinstance(d, dict):
                        continue
                    if 'files' in d and isinstance(d['files'], list):
                        groups.append(d['files'])
                return groups
            if isinstance(duplicates[0], list):
                return duplicates

        if isinstance(duplicates, dict):
            groups = []
            for _h, files in duplicates.items():
                if isinstance(files, list) and len(files) > 1:
                    groups.append(files)
            return groups

        return []

    def generate(self, filename="enhanced_disk_report.html"):
        """生成增强版HTML报告"""
        html_content = self._generate_html_content()
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)

    # ---------------- UI helpers ----------------
    def _nav(self):
        return """
        <div class="nav">
          <div class="nav-left">
            <div class="brand">磁盘扫描报告</div>
            <div class="nav-links">
              <a href="#overview">概览</a>
              <a href="#charts">图表</a>
              <a href="#tree">目录树</a>
              <a href="#flat">扁平目录</a>
              <a href="#dups">重复文件</a>
              <a href="#clean">可清理</a>
              <a href="#security">安全建议</a>
            </div>
          </div>
          <div class="nav-right">
            <button class="btn" id="toggleTheme" title="切换浅色/深色">🌓</button>
            <button class="btn" id="toTop" title="返回顶部">⬆</button>
          </div>
        </div>
        """

    def _kpi_cards(self):
        root = _esc(self.data.get('root_path', self.data.get('path', '.')))
        total_size = format_size(self.data.get('total_size', 0))
        usage = f"{self.disk_usage_percent:.1f}%"
        return f"""
        <div class="kpis">
          <div class="kpi">
            <div class="kpi-label">扫描路径</div>
            <div class="kpi-value monospace" title="{root}">{root}</div>
          </div>
          <div class="kpi">
            <div class="kpi-label">总占用空间</div>
            <div class="kpi-value">{total_size}</div>
          </div>
          <div class="kpi">
            <div class="kpi-label">磁盘使用率</div>
            <div class="kpi-value">{usage}</div>
          </div>
          <div class="kpi">
            <div class="kpi-label">生成时间</div>
            <div class="kpi-value">{_esc(self.current_time)}</div>
          </div>
        </div>
        """

    # ---------------- HTML generation ----------------
    def _generate_html_content(self):
        pie_data = self._prepare_pie_data()
        trend_data = self._prepare_trend_data()

        # 使用 json.dumps 输出到 JS（更稳）
        pie_json = json.dumps(pie_data, ensure_ascii=False)
        trend_json = json.dumps(trend_data, ensure_ascii=False)

        dir_tree_html = self._render_dir_tree(self.data.get('dir_tree', {}), level=0)
        flat_dirs_html = self._render_flat_dirs()
        duplicate_files_html = self._render_duplicate_files()
        cleanable_files_html = self._render_cleanable_files()
        security_suggestions_html = self._render_security_suggestions()

        usage_badge = self._get_usage_badge(self.disk_usage_percent)

        return f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>磁盘扫描报告 - {_esc(self.data.get('root_path', self.data.get('path', '.')))}</title>
  <style>
    :root {{
      --bg: #0b1220;
      --panel: rgba(255,255,255,0.06);
      --panel2: rgba(255,255,255,0.08);
      --text: rgba(255,255,255,0.92);
      --muted: rgba(255,255,255,0.70);
      --border: rgba(255,255,255,0.12);
      --trend-axis-stroke: rgba(255,255,255,0.28);
      --trend-axis-text: rgba(255,255,255,0.78);
      --trend-grid-stroke: rgba(255,255,255,0.10);
      --accent: #4ea3ff;
      --accent2:#7c4dff;
      --good:#2ecc71;
      --warn:#f39c12;
      --bad:#e74c3c;
      --shadow: 0 10px 30px rgba(0,0,0,.35);
      --radius: 16px;
      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }}
    [data-theme="light"] {{
      --bg: #f5f7fa;
      --panel: #ffffff;
      --panel2: #ffffff;
      --text: #1a1a1a;
      --muted: #5f6b7a;
      --border: rgba(0,0,0,0.08);
      --trend-axis-stroke: #94a3b8;
      --trend-axis-text: #64748b;
      --trend-grid-stroke: #e5e7eb;
      --accent: #1e88e5;
      --accent2:#7c4dff;
      --shadow: 0 10px 30px rgba(0,0,0,.08);
    }}
    * {{ box-sizing: border-box; font-family: "Microsoft YaHei", Arial, sans-serif; }}
    body {{
      margin: 0;
      padding: 0;
      background: radial-gradient(1200px 600px at 20% 0%, rgba(78,163,255,.22), transparent 60%),
                  radial-gradient(900px 500px at 80% 10%, rgba(124,77,255,.18), transparent 60%),
                  var(--bg);
      color: var(--text);
    }}
    a {{ color: inherit; text-decoration: none; }}
    .container {{
      width: 95%;
      max-width: 1400px;
      margin: 86px auto 30px auto;
    }}
    .nav {{
      position: fixed;
      top: 0; left: 0; right: 0;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 18px;
      background: rgba(0,0,0,0.35);
      backdrop-filter: blur(10px);
      border-bottom: 1px solid var(--border);
      z-index: 99;
    }}
    [data-theme="light"] .nav {{
      background: rgba(255,255,255,0.72);
    }}
    .nav-left {{
      display: flex;
      align-items: center;
      gap: 14px;
      min-width: 0;
    }}
    .brand {{
      font-weight: 800;
      letter-spacing: .5px;
      font-size: 16px;
      white-space: nowrap;
    }}
    .nav-links {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
      opacity: .95;
    }}
    .nav-links a {{
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid transparent;
      color: var(--muted);
      font-size: 13px;
      transition: all .15s ease;
    }}
    .nav-links a:hover {{
      color: var(--text);
      border-color: var(--border);
      background: var(--panel);
    }}
    .nav-right {{ display:flex; gap:8px; }}
    .btn {{
      border: 1px solid var(--border);
      background: var(--panel);
      color: var(--text);
      padding: 8px 10px;
      border-radius: 12px;
      cursor: pointer;
      box-shadow: none;
      transition: transform .08s ease, background .15s ease, border .15s ease;
    }}
    .btn:hover {{ background: var(--panel2); }}
    .btn:active {{ transform: translateY(1px); }}

    .hero {{
      background: linear-gradient(135deg, rgba(78,163,255,.22), rgba(124,77,255,.18));
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 20px;
      box-shadow: var(--shadow);
      margin-bottom: 18px;
    }}
    .hero-top {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .hero h1 {{
      margin: 0;
      font-size: 26px;
      letter-spacing: .2px;
    }}
    .meta {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
    }}
    .badge {{
      display:inline-flex;
      align-items:center;
      gap:6px;
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 12px;
      border: 1px solid var(--border);
      background: var(--panel);
      color: var(--text);
      white-space: nowrap;
    }}
    .badge-dot {{
      width: 8px; height: 8px;
      border-radius: 50%;
      background: var(--accent);
      display:inline-block;
    }}
    .badge-good .badge-dot {{ background: var(--good); }}
    .badge-warn .badge-dot {{ background: var(--warn); }}
    .badge-bad .badge-dot  {{ background: var(--bad); }}

    .kpis {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-top: 14px;
    }}
    @media (max-width: 980px) {{
      .kpis {{ grid-template-columns: repeat(2, minmax(0,1fr)); }}
    }}
    @media (max-width: 520px) {{
      .kpis {{ grid-template-columns: 1fr; }}
      .nav-links {{ display:none; }}
    }}
    .kpi {{
      background: rgba(255,255,255,0.07);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 12px;
    }}
    [data-theme="light"] .kpi {{
      background: var(--panel);
    }}
    .kpi-label {{ color: var(--muted); font-size: 12px; }}
    .kpi-value {{
      margin-top: 6px;
      font-size: 14px;
      font-weight: 700;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .monospace {{ font-family: var(--mono); }}

    .section {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 16px;
      box-shadow: var(--shadow);
      margin-bottom: 16px;
    }}
    .section h2 {{
      margin: 0 0 12px 0;
      font-size: 18px;
      display:flex;
      align-items:center;
      gap:10px;
    }}
    .section h2 .pill {{
      font-size: 12px;
      color: var(--muted);
      border: 1px solid var(--border);
      padding: 4px 8px;
      border-radius: 999px;
      background: rgba(255,255,255,0.06);
    }}

    details.block {{
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.06);
      border-radius: 14px;
      padding: 10px 12px;
    }}
    [data-theme="light"] details.block {{
      background: rgba(0,0,0,0.02);
    }}
    details.block > summary {{
      cursor: pointer;
      list-style: none;
      display:flex;
      align-items:center;
      justify-content: space-between;
      gap:10px;
    }}
    details.block > summary::-webkit-details-marker {{ display:none; }}
    .summary-left {{ display:flex; align-items:center; gap:10px; min-width:0; }}
    .caret {{
      width: 10px; height: 10px;
      border-right: 2px solid var(--muted);
      border-bottom: 2px solid var(--muted);
      transform: rotate(-45deg);
      transition: transform .15s ease;
    }}
    details[open] .caret {{ transform: rotate(45deg); }}
    .summary-title {{
      font-weight: 800;
      font-size: 14px;
      overflow:hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      max-width: 70vw;
    }}
    .summary-actions {{ display:flex; align-items:center; gap:8px; flex-wrap: wrap; }}
    .muted {{ color: var(--muted); font-size: 12px; }}

    .grid2 {{
      display:grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }}
    @media (max-width: 980px) {{
      .grid2 {{ grid-template-columns: 1fr; }}
    }}
    .chart-card {{
      background: rgba(255,255,255,0.06);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 12px;
    }}
    [data-theme="light"] .chart-card {{
      background: var(--panel);
    }}

    /* SVG charts (no canvas) */
    .svg-donut-wrap, .svg-line-wrap {{ width: 100%; }}
    .svg-donut-grid {{ display: grid; grid-template-columns: 320px 1fr; gap: 12px; align-items: center; }}
    @media (max-width: 980px) {{ .svg-donut-grid {{ grid-template-columns: 1fr; }} }}
    .svg-donut-box {{ width: 100%; max-width: 320px; margin: 0 auto; aspect-ratio: 1 / 1; }}
    .svg-donut-box svg {{ width: 100%; height: 100%; display: block; }}
    .svg-legend {{ display: flex; flex-direction: column; gap: 8px; }}
    .svg-legend-row {{ display:flex; align-items:center; gap:10px; border:1px solid var(--border); background: rgba(255,255,255,0.04); padding:8px 10px; border-radius: 12px; }}
    [data-theme="light"] .svg-legend-row {{ background: rgba(0,0,0,0.02); }}
    .svg-legend-row .swatch {{ width: 10px; height: 10px; border-radius: 3px; flex: 0 0 auto; }}
    .svg-legend-row .lbl {{ font-weight: 800; font-size: 12px; }}
    .svg-legend-row .val {{ margin-left:auto; color: var(--muted); font-size: 12px; }}

    .svg-line-stack {{ display:flex; flex-direction: column; gap: 10px; }}
    .svg-line-box {{ width: 100%; aspect-ratio: 16 / 7; min-height: 240px; }}
    .svg-line-box svg {{ width: 100%; height: 100%; display:block; }}
    .svg-line-legend {{ display:flex; gap:10px; flex-wrap:wrap; color: var(--muted); font-size: 12px; }}
    .svg-line-legend .chip {{ display:inline-flex; align-items:center; gap:8px; padding:6px 10px; border-radius: 999px; border:1px solid var(--border); background: rgba(255,255,255,0.04); }}
    [data-theme="light"] .svg-line-legend .chip {{ background: rgba(0,0,0,0.02); }}
    .svg-line-legend .chip i {{ width: 10px; height: 10px; border-radius: 3px; display:inline-block; }}
    .chart-title {{
      display:flex; align-items:center; justify-content:space-between;
      margin-bottom: 8px;
      gap: 10px;
    }}
    .chart-title h3 {{ margin:0; font-size: 14px; }}
    canvas {{ width: 100% !important; height: 320px !important; }}

    table {{
      width: 100%;
      border-collapse: collapse;
      border-radius: 14px;
      overflow: hidden;
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.04);
    }}
    [data-theme="light"] table {{
      background: var(--panel);
    }}
    thead th {{
      position: sticky;
      top: 0;
      /* 表头背景色：无色（透明），只保留边框与文字 */
      background: transparent;
      color: var(--text);
      text-align: left;
      font-weight: 800;
      font-size: 12px;
      padding: 10px;
      vertical-align: middle;
      border-bottom: 1px solid var(--border);
      z-index: 1;
    }}
    [data-theme="light"] thead th {{
      /* 浅色模式同样保持透明 */
      background: transparent;
    }}
    tbody td {{
      padding: 10px;
      border-bottom: 1px solid var(--border);
      vertical-align: middle;
      font-size: 12px;
      color: var(--text);
    }}
    tbody tr:nth-child(2n) td {{
      background: rgba(255,255,255,0.03);
    }}
    [data-theme="light"] tbody tr:nth-child(2n) td {{
      background: rgba(0,0,0,0.02);
    }}
    tbody tr:hover td {{
      background: rgba(78,163,255,0.10);
    }}

    .toolbar {{
      display:flex;
      gap: 10px;
      align-items:center;
      justify-content: space-between;
      flex-wrap: wrap;
      margin-bottom: 10px;
    }}
    .search {{
      display:flex;
      align-items:center;
      gap: 8px;
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.06);
      border-radius: 12px;
      padding: 8px 10px;
      min-width: 280px;
    }}
    [data-theme="light"] .search {{
      background: rgba(0,0,0,0.02);
    }}
    .search input {{
      border: none;
      outline: none;
      background: transparent;
      color: var(--text);
      width: 260px;
      font-size: 12px;
    }}
    .path {{
      word-break: break-all;
      font-family: var(--mono);
      color: var(--text);
      font-size: 12px;
    }}
    .copy {{
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.06);
      color: var(--text);
      border-radius: 10px;
      padding: 6px 8px;
      cursor: pointer;
      font-size: 12px;
    }}
    [data-theme="light"] .copy {{
      background: rgba(0,0,0,0.02);
    }}
    .copy:active {{ transform: translateY(1px); }}

    /* 目录树：资源管理器风格（行列表），避免“嵌套方块”造成的繁复感 */
    .tree-wrap {{ padding: 6px 0; }}

    details.tree-folder {{ margin: 0; padding: 0; border: 0; background: transparent; }}
    details.tree-folder > summary {{ list-style: none; }}
    details.tree-folder > summary::-webkit-details-marker {{ display:none; }}

    .tree-row {{
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 12px;
      padding-left: calc(12px + var(--indent, 0px));
      border-bottom: 1px solid var(--border);
      background: transparent;
    }}
    .tree-row:hover {{ background: rgba(0,0,0,0.04); }}
    @media (prefers-color-scheme: dark) {{
      .tree-row:hover {{ background: rgba(255,255,255,0.06); }}
    }}

    .tree-chevron {{ width: 14px; text-align: center; color: var(--muted); flex: 0 0 auto; transition: transform 0.12s ease; }}
    details.tree-folder[open] > summary .tree-chevron {{ transform: rotate(90deg); }}

    .tree-icon {{ width: 18px; height: 18px; display: inline-flex; align-items: center; justify-content: center; flex: 0 0 auto; }}
    .tree-icon.folder {{ color: var(--accent); }}
    .tree-icon.file {{ color: rgba(100,116,139,0.9); }}

    .tree-name {{
      font-weight: 800;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      min-width: 0;
    }}

    .tree-spacer {{ flex: 1; min-width: 8px; }}

    .tree-meta {{ display:flex; align-items:center; gap: 10px; flex-wrap: wrap; }}
    .tree-size {{ color: var(--muted); font-size: 12px; }}

    .tree-children {{ margin-left: 12px; border-left: 1px dashed var(--border); }}

    .bar {{
      height: 8px;
      width: 120px;
      background: rgba(255,255,255,0.10);
      border-radius: 999px;
      border: 1px solid var(--border);
      overflow: hidden;
    }}
    .bar > i {{
      display:block;
      height:100%;
      width:0%;
      background: linear-gradient(90deg, var(--accent), var(--accent2));
    }}

    .hint {{
      color: var(--muted);
      font-size: 12px;
    }}
  </style>
</head>
<body>
  {self._nav()}

  <div class="container">
    <div class="hero">
      <div class="hero-top">
        <h1>磁盘扫描报告</h1>
        <span class="badge {usage_badge}"><span class="badge-dot"></span>使用率 {self.disk_usage_percent:.1f}%</span>
      </div>
      <div class="meta">
        扫描路径: <strong class="monospace">{_esc(self.data.get('root_path', self.data.get('path', '.')))}</strong>
      </div>
      {self._kpi_cards()}
    </div>

    <div class="section" id="overview">
      <h2>概览 <span class="pill">建议阈值 85%</span></h2>
      <table>
        <thead>
          <tr><th>指标</th><th>当前值</th><th>参考阈值</th><th>建议</th></tr>
        </thead>
        <tbody>
          <tr>
            <td>磁盘使用率</td>
            <td>{self.disk_usage_percent:.1f}%</td>
            <td>85%</td>
            <td>{self._get_disk_usage_suggestion(self.disk_usage_percent)}</td>
          </tr>
        </tbody>
      </table>
      <div class="hint" style="margin-top:10px;">提示：你可以使用顶部导航快速跳转，或使用每个表格上的搜索框进行过滤。</div>
    </div>

    <div class="section" id="charts">
      <h2>图表 <span class="pill">文件类型 / 历史趋势</span></h2>
      <div class="grid2">
        <div class="chart-card">
          <div class="chart-title">
            <h3>文件类型分布</h3>
            <span class="muted">占比 &gt; 2% 自动单列</span>
          </div>
          <div id="fileTypeChart" class="svg-donut-wrap"></div>
        </div>
        <div class="chart-card">
          <div class="chart-title">
            <h3>历史趋势</h3>
            <span class="muted">已用空间(GB) + 使用率(%)</span>
          </div>
          <div id="trendChart" class="svg-line-wrap"></div>
        </div>
      </div>
    </div>

    <div class="section" id="tree">
      <h2>目录树（按大小） <span class="pill">可折叠</span></h2>
      <details class="block" open>
        <summary>
          <div class="summary-left">
            <span class="caret"></span>
            <span class="summary-title">展开/折叠目录树</span>
          </div>
          <div class="summary-actions">
            <span class="muted">默认仅展示每层 Top 100（防止页面过大）</span>
          </div>
        </summary>
        <div class="tree-wrap">
          {dir_tree_html}
        </div>
      </details>
    </div>

    <div class="section" id="flat">
      <h2>扁平目录统计（Top） <span class="pill">可搜索</span></h2>
      {flat_dirs_html}
    </div>

    <div class="section" id="dups">
      <h2>重复文件 <span class="pill">可搜索 + 复制路径</span></h2>
      {duplicate_files_html}
    </div>

    <div class="section" id="clean">
      <h2>可清理文件/目录（Top） <span class="pill">可搜索 + 风险等级</span></h2>
      {cleanable_files_html}
    </div>

    <div class="section" id="security">
      <h2>安全建议</h2>
      {security_suggestions_html}
    </div>
  </div>

<script>
  const pieData = {pie_json};
  const trendData = {trend_json};

  // Theme
  (function() {{
    const saved = localStorage.getItem("theme") || "dark";
    document.documentElement.setAttribute("data-theme", saved);
    const btn = document.getElementById("toggleTheme");
    btn.addEventListener("click", () => {{
      const cur = document.documentElement.getAttribute("data-theme") || "dark";
      const next = cur === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("theme", next);
    }});
    document.getElementById("toTop").addEventListener("click", () => window.scrollTo({{top:0, behavior:"smooth"}}));
  }})();

  function clamp(v, a, b) {{ return Math.max(a, Math.min(b, v)); }}

  // ---------- SVG charts (no Chart.js / no canvas) ----------
  function fmtBytes(bytes) {{
    const b = Number(bytes) || 0;
    const units = ["B","KB","MB","GB","TB","PB"];
    let v = b;
    let i = 0;
    while (v >= 1024 && i < units.length - 1) {{ v /= 1024; i++; }}
    return `${{v.toFixed(2)}} ${{units[i]}}`;
  }}

  function softPalette(n) {{
    const base = [
      "#8EC5FC", "#E0C3FC", "#A8EDEA", "#FED6E3",
      "#FAD0C4", "#FFD1FF", "#C2E9FB", "#D4FC79",
      "#96E6A1", "#FFECB3", "#B5FFFC", "#C6FFDD"
    ];
    const out = [];
    for (let i = 0; i < n; i++) out.push(base[i % base.length]);
    return out;
  }}

  function renderDonut(containerId, labels, values) {{
    const el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = "";
    const total = values.reduce((a,b)=>a+(Number(b)||0), 0) || 1;

    const size = 260;
    const cx = size/2, cy = size/2;
    const r = 92;
    const stroke = 26;
    const C = 2 * Math.PI * r;
    const colors = softPalette(labels.length);

    const svg = document.createElementNS("http://www.w3.org/2000/svg","svg");
    svg.setAttribute("viewBox", `0 0 ${{size}} ${{size}}`);
    svg.setAttribute("preserveAspectRatio","xMidYMid meet");
    svg.classList.add("svg-donut");

    // bg ring
    const bg = document.createElementNS("http://www.w3.org/2000/svg","circle");
    bg.setAttribute("cx", cx);
    bg.setAttribute("cy", cy);
    bg.setAttribute("r", r);
    bg.setAttribute("fill","none");
    bg.setAttribute("stroke","rgba(255,255,255,0.10)");
    bg.setAttribute("stroke-width", stroke);
    svg.appendChild(bg);

    let offset = 0;
    for (let i=0;i<labels.length;i++) {{
      const v = Number(values[i]) || 0;
      const seg = (v/total) * C;

      const c = document.createElementNS("http://www.w3.org/2000/svg","circle");
      c.setAttribute("cx", cx);
      c.setAttribute("cy", cy);
      c.setAttribute("r", r);
      c.setAttribute("fill","none");
      c.setAttribute("stroke", colors[i]);
      c.setAttribute("stroke-width", stroke);
      c.setAttribute("stroke-linecap","butt");
      c.setAttribute("transform", `rotate(-90 ${{cx}} ${{cy}})`);
      c.setAttribute("stroke-dasharray", `${{seg}} ${{C - seg}}`);
      c.setAttribute("stroke-dashoffset", `${{-offset}}`);
      svg.appendChild(c);

      offset += seg;
    }}

    // center label
    const t1 = document.createElementNS("http://www.w3.org/2000/svg","text");
    t1.setAttribute("x", cx);
    t1.setAttribute("y", cy - 4);
    t1.setAttribute("text-anchor","middle");
    t1.setAttribute("fill","currentColor");
    t1.setAttribute("font-size","14");
    t1.setAttribute("font-weight","800");
    t1.textContent = "文件类型";
    svg.appendChild(t1);

    const t2 = document.createElementNS("http://www.w3.org/2000/svg","text");
    t2.setAttribute("x", cx);
    t2.setAttribute("y", cy + 16);
    t2.setAttribute("text-anchor","middle");
    t2.setAttribute("fill","rgba(255,255,255,0.70)");
    t2.setAttribute("font-size","12");
    t2.textContent = `${{labels.length}} 类`;
    svg.appendChild(t2);

    // legend
    const legend = document.createElement("div");
    legend.className = "svg-legend";
    for (let i=0;i<labels.length;i++) {{
      const v = Number(values[i]) || 0;
      const pct = ((v/total)*100);
      const row = document.createElement("div");
      row.className = "svg-legend-row";
      row.innerHTML = `
        <span class="swatch" style="background:${{colors[i]}}"></span>
        <span class="lbl">${{labels[i]}}</span>
        <span class="val">${{pct.toFixed(1)}}% · ${{fmtBytes(v)}}</span>
      `;
      legend.appendChild(row);
    }}

    const wrap = document.createElement("div");
    wrap.className = "svg-donut-grid";
    const box = document.createElement("div");
    box.className = "svg-donut-box";
    box.appendChild(svg);
    wrap.appendChild(box);
    wrap.appendChild(legend);

    el.appendChild(wrap);
  }}

  function renderTrend(containerId, labels, gbValues, usageValues) {{
    const el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = "";

    const W = 720, H = 320;
    const padL = 44, padR = 44, padT = 18, padB = 36;
    const innerW = W - padL - padR;
    const innerH = H - padT - padB;

    const xs = labels.map((_,i)=>i);
    const maxX = Math.max(1, xs.length-1);

    const y0 = gbValues.map(v=>Number(v)||0);
    const y1 = usageValues.map(v=>Number(v)||0);

    const minGb = 0;
    const maxGb = Math.max(1, ...y0);
    const minPct = 0;
    const maxPct = 100;

    function xScale(i) {{ return padL + (i/maxX)*innerW; }}
    function yGb(v) {{ return padT + (1 - (v-minGb)/(maxGb-minGb))*innerH; }}
    function yPct(v) {{ return padT + (1 - (v-minPct)/(maxPct-minPct))*innerH; }}

    const svg = document.createElementNS("http://www.w3.org/2000/svg","svg");
    svg.setAttribute("viewBox", `0 0 ${{W}} ${{H}}`);
    svg.setAttribute("preserveAspectRatio","xMidYMid meet");
    svg.classList.add("svg-line");

    const rootCS = getComputedStyle(document.documentElement);
    const axisStroke = (rootCS.getPropertyValue("--trend-axis-stroke") || "rgba(0,0,0,0.35)").trim();
    const axisText = (rootCS.getPropertyValue("--trend-axis-text") || "rgba(0,0,0,0.65)").trim();
    const gridStroke = (rootCS.getPropertyValue("--trend-grid-stroke") || "rgba(0,0,0,0.12)").trim();

    // gridlines (5)
    for (let k=0;k<=5;k++) {{
      const y = padT + (k/5)*innerH;
      const ln = document.createElementNS("http://www.w3.org/2000/svg","line");
      ln.setAttribute("x1", padL);
      ln.setAttribute("x2", W - padR);
      ln.setAttribute("y1", y);
      ln.setAttribute("y2", y);
      ln.setAttribute("stroke", gridStroke);
      ln.setAttribute("stroke-width","1");
      svg.appendChild(ln);
    }}

    // axes
    const ax = document.createElementNS("http://www.w3.org/2000/svg","line");
    ax.setAttribute("x1", padL);
    ax.setAttribute("x2", W - padR);
    ax.setAttribute("y1", H - padB);
    ax.setAttribute("y2", H - padB);
    ax.setAttribute("stroke", axisStroke);
    ax.setAttribute("stroke-width","1.2");
    svg.appendChild(ax);

    const ayL = document.createElementNS("http://www.w3.org/2000/svg","line");
    ayL.setAttribute("x1", padL);
    ayL.setAttribute("x2", padL);
    ayL.setAttribute("y1", padT);
    ayL.setAttribute("y2", H - padB);
    ayL.setAttribute("stroke", axisStroke);
    ayL.setAttribute("stroke-width","1.2");
    svg.appendChild(ayL);

    const ayR = document.createElementNS("http://www.w3.org/2000/svg","line");
    ayR.setAttribute("x1", W - padR);
    ayR.setAttribute("x2", W - padR);
    ayR.setAttribute("y1", padT);
    ayR.setAttribute("y2", H - padB);
    ayR.setAttribute("stroke", axisStroke);
    ayR.setAttribute("stroke-width","1.2");
    svg.appendChild(ayR);

    const [cGb, cPct] = ["#8EC5FC", "#FED6E3"]; // 柔和蓝 & 柔和粉

    function poly(points, color) {{
      const pl = document.createElementNS("http://www.w3.org/2000/svg","polyline");
      pl.setAttribute("fill","none");
      pl.setAttribute("stroke", color);
      pl.setAttribute("stroke-width","2.5");
      pl.setAttribute("stroke-linecap","round");
      pl.setAttribute("stroke-linejoin","round");
      pl.setAttribute("points", points.map(p=>`${{p[0]}},${{p[1]}}`).join(" "));
      return pl;
    }}

    const ptsGb = y0.map((v,i)=>[xScale(i), yGb(v)]);
    const ptsPct = y1.map((v,i)=>[xScale(i), yPct(v)]);

    svg.appendChild(poly(ptsGb, cGb));
    svg.appendChild(poly(ptsPct, cPct));

    // x labels (show up to 6)
    const step = Math.ceil(labels.length / 6) || 1;
    for (let i=0;i<labels.length;i+=step) {{
      const tx = document.createElementNS("http://www.w3.org/2000/svg","text");
      tx.setAttribute("x", xScale(i));
      tx.setAttribute("y", H - 14);
      tx.setAttribute("text-anchor","middle");
      tx.setAttribute("fill","var(--text)");
      tx.setAttribute("font-size","10.5");
      tx.textContent = String(labels[i]).slice(5); // MM-DD
      svg.appendChild(tx);
    }}

    // y labels left/right
    for (let k=0;k<=4;k++) {{
      const v = (k/4)*maxGb;
      const y = yGb(v);
      const tx = document.createElementNS("http://www.w3.org/2000/svg","text");
      tx.setAttribute("x", padL - 8);
      tx.setAttribute("y", y + 3);
      tx.setAttribute("text-anchor","end");
      tx.setAttribute("fill","var(--text)");
      tx.setAttribute("font-size","10.5");
      tx.textContent = v.toFixed(0);
      svg.appendChild(tx);

      const p = (k/4)*100;
      const y2 = yPct(p);
      const tx2 = document.createElementNS("http://www.w3.org/2000/svg","text");
      tx2.setAttribute("x", W - padR + 8);
      tx2.setAttribute("y", y2 + 3);
      tx2.setAttribute("text-anchor","start");
      tx2.setAttribute("fill","var(--text)");
      tx2.setAttribute("font-size","10.5");
      tx2.textContent = `${{p.toFixed(0)}}%`;
      svg.appendChild(tx2);
    }}

    // legend
    const legend = document.createElement("div");
    legend.className = "svg-line-legend";
    legend.innerHTML = `
      <span class="chip"><i style="background:${{cGb}}"></i> 已用空间(GB)</span>
      <span class="chip"><i style="background:${{cPct}}"></i> 使用率(%)</span>
    `;

    const wrap = document.createElement("div");
    wrap.className = "svg-line-stack";
    const box = document.createElement("div");
    box.className = "svg-line-box";
    box.appendChild(svg);
    wrap.appendChild(box);
    wrap.appendChild(legend);

    el.appendChild(wrap);
  }}

  function renderAllCharts() {{
    renderDonut("fileTypeChart", pieData.labels || [], pieData.values || []);
    renderTrend("trendChart", trendData.labels || [], trendData.values || [], trendData.usage_values || []);
  }}

  renderAllCharts();

  // re-render on theme toggle (colors are mostly pastel, but text/grid uses currentColor)
  document.getElementById("toggleTheme").addEventListener("click", () => {{
    setTimeout(renderAllCharts, 50);
  }});


  // table filter + copy helpers
  function attachTableFilter(inputId, tableId) {{
    const input = document.getElementById(inputId);
    const table = document.getElementById(tableId);
    if (!input || !table) return;
    input.addEventListener("input", () => {{
      const q = (input.value || "").toLowerCase().trim();
      const rows = table.querySelectorAll("tbody tr");
      rows.forEach(r => {{
        const text = (r.innerText || "").toLowerCase();
        r.style.display = text.includes(q) ? "" : "none";
      }});
    }});
  }}

  async function copyText(text) {{
    try {{
      await navigator.clipboard.writeText(text);
      return true;
    }} catch (e) {{
      // fallback
      try {{
        const ta = document.createElement("textarea");
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        return true;
      }} catch (_) {{
        return false;
      }}
    }}
  }}

  document.addEventListener("click", async (e) => {{
    const btn = e.target.closest("[data-copy]");
    if (!btn) return;
    const text = btn.getAttribute("data-copy") || "";
    const ok = await copyText(text);
    btn.textContent = ok ? "已复制" : "复制失败";
    setTimeout(() => btn.textContent = "复制", 900);
  }});

  // smooth anchor scroll
  document.querySelectorAll('a[href^="#"]').forEach(a => {{
    a.addEventListener("click", (e) => {{
      const id = a.getAttribute("href");
      const el = document.querySelector(id);
      if (el) {{
        e.preventDefault();
        el.scrollIntoView({{behavior:"smooth", block:"start"}});
      }}
    }});
  }});

  // fill bars
  document.querySelectorAll(".bar[data-pct]").forEach(b => {{
    const pct = parseFloat(b.getAttribute("data-pct") || "0");
    const w = clamp(pct, 0, 100);
    const inner = b.querySelector("i");
    if (inner) inner.style.width = w + "%";
  }});
</script>
</body>
</html>
"""

    def _get_usage_badge(self, usage):
        if usage < 70:
            return "badge-good"
        elif usage < 85:
            return "badge-warn"
        else:
            return "badge-bad"

    def _prepare_pie_data(self):
        file_types = self._coerce_file_types(self.data.get('file_types', {}))
        total_size = sum(file_types.values()) if isinstance(file_types, dict) else 0

        filtered_types = {}
        other_size = 0
        min_percentage = 2

        if isinstance(file_types, dict):
            for ext, size in file_types.items():
                percentage = (size / total_size) * 100 if total_size > 0 else 0
                if percentage >= min_percentage:
                    filtered_types[ext] = size
                else:
                    other_size += size

        if other_size > 0:
            filtered_types['其他'] = other_size

        labels = list(filtered_types.keys())
        values = list(filtered_types.values())
        return {'labels': labels, 'values': values}

    def _prepare_trend_data(self):
        history = self._coerce_history(self.data.get('history_data', []))

        if not history:
            from datetime import datetime, timedelta
            now = datetime.now()
            history = []
            for i in range(30):
                date = now - timedelta(days=29 - i)
                usage = 40 + (i % 10) * 3 + (i // 10) * 2
                size = (200 + i * 2.5) * 1024 * 1024 * 1024
                history.append({'date': date.strftime('%Y-%m-%d'), 'usage': usage, 'size': size})

        labels = [item.get('date', '') for item in history]
        values = [((item.get('size', 0) or 0) / (1024 * 1024 * 1024)) for item in history]
        usage_values = [
            (item.get('usage', self.disk_usage_percent)
             if item.get('usage', None) is not None else self.disk_usage_percent)
            for item in history
        ]
        return {'labels': labels, 'values': values, 'usage_values': usage_values}

    def _render_dir_tree(self, dir_node, level):
        """渲染目录树（资源管理器风格，不再使用嵌套方块）"""
        if not dir_node:
            return '<div class="hint">无数据</div>'

        name = _esc(dir_node.get('name', ''))
        size = dir_node.get('size', 0)
        pct = dir_node.get('percentage', 0) or 0
        children = dir_node.get('children')

        indent_px = level * 18  # 更像文件管理器的缩进
        bar = f'<span class="bar" data-pct="{pct:.2f}"><i></i></span>'

        # 文件节点
        if children is None:
            return f"""
        <div class="tree-row tree-file" style="--indent:{indent_px}px">
          <span class="tree-chevron" aria-hidden="true"></span>
          <span class="tree-icon file" aria-hidden="true">📄</span>
          <span class="tree-name" title="{name}">{name}</span>
          <span class="tree-spacer"></span>
          <span class="tree-size">{format_size(size)}</span>
        </div>
            """.strip()

        # 目录节点
        open_attr = "open" if level <= 1 else ""
        folder_header = f"""
        <span class="tree-chevron" aria-hidden="true">▶</span>
        <span class="tree-icon folder" aria-hidden="true">📁</span>
        <span class="tree-name" title="{name}">{name}</span>
        <span class="tree-spacer"></span>
        <span class="tree-meta">
          <span class="tree-size">{format_size(size)} ({pct:.2f}%)</span>
          {bar}
        </span>
        """.strip()

        html_out = [f'<details class="tree-folder" {open_attr}>',
                    f'<summary class="tree-row" style="--indent:{indent_px}px">{folder_header}</summary>',
                    '<div class="tree-children">']

        if isinstance(children, list) and children:
            for child in children[:100]:
                html_out.append(self._render_dir_tree(child, level + 1))
        else:
            html_out.append('<div class="hint" style="padding:10px 12px;">无子项</div>')

        html_out.append('</div></details>')
        return "\n".join(html_out)

    def _render_flat_dirs(self):
        flat_dirs = self.data.get('flat_dirs', [])
        if not flat_dirs:
            return '<div class="hint">无目录统计数据</div>'

        # 工具栏 + 搜索（不改变内容，只增加过滤能力）
        html_out = [
            """
            <div class="toolbar">
              <div class="search">
                🔎 <input id="flatSearch" placeholder="搜索目录路径/大小/占比..." />
              </div>
              <div class="muted">提示：可使用浏览器搜索/本框过滤</div>
            </div>
            <table id="flatTable">
              <thead><tr><th>目录</th><th>大小</th><th>占比</th><th>操作</th></tr></thead>
              <tbody>
            """
        ]

        for d in flat_dirs[:50]:
            p = d.get('path', '')
            html_out.append(f"""
              <tr>
                <td class="path">{_esc(p)}</td>
                <td>{format_size(d.get('size',0))}</td>
                <td>{(d.get('percentage',0) or 0):.2f}%</td>
                <td><button class="copy" data-copy="{_esc(p)}">复制</button></td>
              </tr>
            """)

        html_out.append("</tbody></table>")
        html_out.append("""
          <script>attachTableFilter("flatSearch","flatTable");</script>
        """)
        return "\n".join(html_out)

    def _render_duplicate_files(self):
        duplicates = self._coerce_duplicates(self.data.get('duplicate_files', []))
        if not duplicates:
            return '<div class="hint">未检测到重复文件</div>'

        html_out = [
            """
            <div class="toolbar">
              <div class="search">
                🔎 <input id="dupSearch" placeholder="搜索路径/大小..." />
              </div>
              <div class="muted">提示：表格很长时建议用过滤</div>
            </div>
            <table id="dupTable">
              <thead><tr><th>文件大小</th><th>重复数量</th><th>文件路径</th><th>操作</th></tr></thead>
              <tbody>
            """
        ]

        for dup_group in duplicates:
            if not dup_group or not isinstance(dup_group[0], dict):
                continue
            size = dup_group[0].get('size', 0)
            count = len(dup_group)

            # 第一行（rowspan）
            first_path = dup_group[0].get('path', '')
            html_out.append(f"""
              <tr>
                <td rowspan="{count}">{format_size(size)}</td>
                <td rowspan="{count}">{count}</td>
                <td class="path">{_esc(first_path)}</td>
                <td><button class="copy" data-copy="{_esc(first_path)}">复制</button></td>
              </tr>
            """)

            # 其余重复文件
            for f in dup_group[1:]:
                p = f.get('path', '')
                html_out.append(f"""
                  <tr>
                    <td class="path">{_esc(p)}</td>
                    <td><button class="copy" data-copy="{_esc(p)}">复制</button></td>
                  </tr>
                """)

        html_out.append("</tbody></table>")
        html_out.append("""
          <script>attachTableFilter("dupSearch","dupTable");</script>
        """)
        return "\n".join(html_out)

    def _render_cleanable_files(self):
        cleanable = self.data.get('cleanable_files', [])
        if not cleanable:
            return '<div class="hint">暂无可清理文件</div>'

        html_out = [
            """
            <div class="toolbar">
              <div class="search">
                🔎 <input id="cleanSearch" placeholder="搜索路径/建议/风险..." />
              </div>
              <div class="muted">提示：仅展示 Top 50（保持原逻辑）</div>
            </div>
            <table id="cleanTable">
              <thead><tr><th>风险</th><th>大小</th><th>路径</th><th>建议</th><th>操作</th></tr></thead>
              <tbody>
            """
        ]

        for item in cleanable[:50]:
            level = int(item.get('risk_level', 3) or 3)
            badge = "badge-good" if level >= 4 else ("badge-warn" if level >= 2 else "badge-bad")
            p = item.get('path', '')
            html_out.append(f"""
              <tr>
                <td><span class="badge {badge}"><span class="badge-dot"></span>L{level}</span></td>
                <td>{format_size(item.get('size',0))}</td>
                <td class="path">{_esc(p)}</td>
                <td>{_esc(item.get('suggestion',''))}</td>
                <td><button class="copy" data-copy="{_esc(p)}">复制</button></td>
              </tr>
            """)

        html_out.append("</tbody></table>")
        html_out.append("""
          <script>attachTableFilter("cleanSearch","cleanTable");</script>
        """)
        return "\n".join(html_out)

    def _render_security_suggestions(self):
        usage = self.disk_usage_percent
        return f"""
        <details class="block" open>
          <summary>
            <div class="summary-left">
              <span class="caret"></span>
              <span class="summary-title">磁盘使用率建议</span>
            </div>
            <div class="summary-actions">
              <span class="badge {self._get_usage_badge(usage)}"><span class="badge-dot"></span>{usage:.1f}%</span>
            </div>
          </summary>
          <div style="margin-top:10px;">
            当前磁盘使用率 <strong>{usage:.1f}%</strong>，{self._get_disk_usage_suggestion(usage)}
          </div>
        </details>
        """

    def _get_disk_usage_suggestion(self, usage):
        """获取磁盘使用率建议（内容保持不变）"""
        if usage < 70:
            return '<span class="badge badge-good"><span class="badge-dot"></span>使用率正常</span> - 无需立即清理'
        elif usage < 85:
            return '<span class="badge badge-warn"><span class="badge-dot"></span>使用率偏高</span> - 建议清理可清理文件'
        else:
            return '<span class="badge badge-bad"><span class="badge-dot"></span>使用率过高</span> - 立即清理大文件和重复文件'
