import os
import time
import random


def format_size(size):
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


class EnhancedHTMLReporter:
    def __init__(self, scan_data):
        """
        初始化报告生成器
        :param scan_data: 包含所有扫描信息的字典
        """
        self.data = scan_data
        self.current_time = time.strftime('%Y-%m-%d %H:%M:%S')

        # 兼容不同版本 analyzer 输出：归一化关键字段，避免 KeyError/类型错误
        self.disk_usage_percent = self._coerce_disk_usage_percent(self.data.get('disk_usage', 0))
        self.data['disk_usage_percent'] = self.disk_usage_percent  # 供模板/JS 使用（可选）

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
                # 有些数据可能是 used/total
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

            # 兼容旧字段
            if size is None:
                # 可能叫 used_bytes / used
                if 'used_bytes' in item:
                    size = item.get('used_bytes')
                elif 'used' in item and isinstance(item.get('used'), (int, float)):
                    size = item.get('used')
            if usage is None:
                if 'used_percent' in item:
                    usage = item.get('used_percent')

            # 兜底
            if date is None:
                date = str(i)
            if size is None:
                size = 0
            if usage is None:
                # 没有 usage 就尝试从 size/total 推；否则用当前盘使用率
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

        # 已经是 list of groups
        if isinstance(duplicates, list):
            if not duplicates:
                return []
            # 如果第一个元素是 dict，可能是 [{'hash':..,'files':[...]}] 或 {'files':...}
            if isinstance(duplicates[0], dict):
                groups = []
                for d in duplicates:
                    if not isinstance(d, dict):
                        continue
                    if 'files' in d and isinstance(d['files'], list):
                        groups.append(d['files'])
                return groups

            # 如果第一个元素是 list，认为是期望结构
            if isinstance(duplicates[0], list):
                return duplicates

        # dict: {hash: [files]}
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

    def _generate_html_content(self):
        """生成完整HTML内容"""
        # 准备各类图表数据
        pie_data = self._prepare_pie_data()
        trend_data = self._prepare_trend_data()
        dir_tree_html = self._render_dir_tree(self.data.get('dir_tree', {}), level=0)
        flat_dirs_html = self._render_flat_dirs()
        duplicate_files_html = self._render_duplicate_files()
        cleanable_files_html = self._render_cleanable_files()
        security_suggestions_html = self._render_security_suggestions()

        return f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>磁盘扫描报告 - {self.data.get('path', self.data.get('root_path', '.'))}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{
            box-sizing: border-box;
            font-family: 'Microsoft YaHei', Arial, sans-serif;
        }}
        body {{
            margin: 0;
            padding: 0;
            background: #f5f7fa;
            color: #333;
        }}
        .container {{
            width: 95%;
            max-width: 1400px;
            margin: 20px auto;
        }}
        .header {{
            background: linear-gradient(135deg, #1e88e5, #1565c0);
            color: white;
            padding: 25px;
            border-radius: 10px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        .header h1 {{
            margin: 0 0 10px 0;
            font-size: 28px;
        }}
        .header .meta {{
            opacity: 0.95;
            font-size: 14px;
            line-height: 1.6;
        }}
        .section {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            margin-bottom: 20px;
        }}
        .section h2 {{
            margin: 0 0 15px 0;
            font-size: 20px;
            border-left: 4px solid #1e88e5;
            padding-left: 10px;
        }}
        .chart-row {{
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
        }}
        .chart-container {{
            flex: 1;
            min-width: 320px;
            background: #fff;
            border-radius: 10px;
            padding: 10px 10px 20px 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 10px;
            border-bottom: 1px solid #eee;
            text-align: left;
            vertical-align: top;
        }}
        th {{
            background: #fafafa;
            font-weight: 600;
        }}
        .tree-item {{
            margin-left: 10px;
            padding: 6px 0;
        }}
        .tree-name {{
            font-weight: 600;
        }}
        .tree-size {{
            color: #666;
            margin-left: 8px;
        }}
        .tree-bar {{
            display: inline-block;
            height: 8px;
            background: #1e88e5;
            border-radius: 4px;
            margin-left: 10px;
            vertical-align: middle;
        }}
        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 12px;
            color: white;
        }}
        .badge-success {{ background: #43a047; }}
        .badge-warning {{ background: #fb8c00; }}
        .badge-danger  {{ background: #e53935; }}
        .muted {{
            color: #777;
            font-size: 12px;
        }}
        .path {{
            word-break: break-all;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
            font-size: 12px;
            color: #444;
        }}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>磁盘扫描报告</h1>
        <div class="meta">
            扫描路径: <strong>{self.data.get('root_path', self.data.get('path', '.'))}</strong> | 
            生成时间: {self.current_time} | 
            总占用空间: <strong>{format_size(self.data.get('total_size', 0))}</strong> |
            当前磁盘使用率: <strong>{self.disk_usage_percent:.1f}%</strong>
        </div>
    </div>

    <div class="section">
        <h2>概览</h2>
        <table>
            <thead>
                <tr>
                    <th>指标</th>
                    <th>当前值</th>
                    <th>参考阈值</th>
                    <th>建议</th>
                </tr>
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
    </div>

    <!-- 图表区域 -->
    <div class="chart-row">
        <div class="chart-container">
            <h2>文件类型分布</h2>
            <canvas id="fileTypeChart"></canvas>
        </div>
        <div class="chart-container">
            <h2>历史趋势</h2>
            <canvas id="trendChart"></canvas>
        </div>
    </div>

    <div class="section">
        <h2>目录树（按大小）</h2>
        {dir_tree_html}
    </div>

    <div class="section">
        <h2>扁平目录统计（Top）</h2>
        {flat_dirs_html}
    </div>

    <div class="section">
        <h2>重复文件</h2>
        {duplicate_files_html}
    </div>

    <div class="section">
        <h2>可清理文件/目录（Top）</h2>
        {cleanable_files_html}
    </div>

    <div class="section">
        <h2>安全建议</h2>
        {security_suggestions_html}
    </div>
</div>

<script>
const pieData = {pie_data};
const trendData = {trend_data};

// 文件类型饼图
const ctxPie = document.getElementById('fileTypeChart').getContext('2d');
new Chart(ctxPie, {{
    type: 'pie',
    data: {{
        labels: pieData.labels,
        datasets: [{{
            data: pieData.values
        }}]
    }},
    options: {{
        responsive: true
    }}
}});

// 趋势图（容量+使用率）
const ctxTrend = document.getElementById('trendChart').getContext('2d');
new Chart(ctxTrend, {{
    type: 'line',
    data: {{
        labels: trendData.labels,
        datasets: [
            {{
                label: '已用空间(GB)',
                data: trendData.values,
                yAxisID: 'y'
            }},
            {{
                label: '使用率(%)',
                data: trendData.usage_values,
                yAxisID: 'y1'
            }}
        ]
    }},
    options: {{
        responsive: true,
        scales: {{
            y: {{
                type: 'linear',
                position: 'left',
                title: {{ display: true, text: 'GB' }}
            }},
            y1: {{
                type: 'linear',
                position: 'right',
                title: {{ display: true, text: '%' }},
                grid: {{ drawOnChartArea: false }}
            }}
        }}
    }}
}});
</script>
</body>
</html>
"""

    def _prepare_pie_data(self):
        """准备饼图数据"""
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
        """准备趋势图数据"""
        history = self._coerce_history(self.data.get('history_data', []))

        # 生成模拟数据（如果没有历史数据）
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
            (item.get('usage', self.disk_usage_percent) if item.get('usage', None) is not None else self.disk_usage_percent)
            for item in history
        ]

        return {'labels': labels, 'values': values, 'usage_values': usage_values}

    def _render_dir_tree(self, dir_node, level):
        """渲染目录树"""
        if not dir_node:
            return '<div class="tree-item">无数据</div>'

        indent = level * 20
        name = dir_node.get('name', '')
        size = dir_node.get('size', 0)
        pct = dir_node.get('percentage', 0)
        bar_width = min(100, max(0, pct))

        html = f'''
        <div class="tree-item" style="margin-left:{indent}px;">
            <span class="tree-name">{name}</span>
            <span class="tree-size">{format_size(size)}</span>
            <span class="muted">({pct:.2f}%)</span>
            <span class="tree-bar" style="width:{bar_width}px;"></span>
        </div>
        '''

        children = dir_node.get('children')
        if isinstance(children, list) and children:
            for child in children[:100]:  # 防止页面过大
                if child.get('children') is None:
                    # 文件
                    html += f'''
                    <div class="tree-item" style="margin-left:{indent+20}px;">
                        <span class="tree-name">{child.get('name','')}</span>
                        <span class="tree-size">{format_size(child.get('size',0))}</span>
                    </div>
                    '''
                else:
                    html += self._render_dir_tree(child, level + 1)

        return html

    def _render_flat_dirs(self):
        flat_dirs = self.data.get('flat_dirs', [])
        if not flat_dirs:
            return '<div>无目录统计数据</div>'

        html = '<table><thead><tr><th>目录</th><th>大小</th><th>占比</th></tr></thead><tbody>'
        for d in flat_dirs[:50]:
            html += f"""
            <tr>
                <td class="path">{d.get('path','')}</td>
                <td>{format_size(d.get('size',0))}</td>
                <td>{d.get('percentage',0):.2f}%</td>
            </tr>
            """
        html += '</tbody></table>'
        return html

    def _render_duplicate_files(self):
        """渲染重复文件列表"""
        duplicates = self._coerce_duplicates(self.data.get('duplicate_files', []))

        if not duplicates:
            return '<div>未检测到重复文件</div>'

        html = '<table><thead><tr><th>文件大小</th><th>重复数量</th><th>文件路径</th></tr></thead><tbody>'

        for dup_group in duplicates:
            if not dup_group:
                continue

            # 兼容：如果组内元素不是 dict，跳过
            if not isinstance(dup_group[0], dict):
                continue

            size = dup_group[0].get('size', 0)
            count = len(dup_group)

            html += f'''
            <tr style="background-color: #f8f9fa;">
                <td rowspan="{count}">{format_size(size)}</td>
                <td rowspan="{count}">{count}</td>
                <td class="path">{dup_group[0].get('path','')}</td>
            </tr>
            '''

            for f in dup_group[1:]:
                html += f'''
                <tr>
                    <td class="path">{f.get('path','')}</td>
                </tr>
                '''

        html += '</tbody></table>'
        return html

    def _render_cleanable_files(self):
        cleanable = self.data.get('cleanable_files', [])
        if not cleanable:
            return '<div>暂无可清理文件</div>'

        html = '<table><thead><tr><th>风险</th><th>大小</th><th>路径</th><th>建议</th></tr></thead><tbody>'
        for item in cleanable[:50]:
            level = int(item.get('risk_level', 3) or 3)
            badge = 'badge-success' if level >= 4 else ('badge-warning' if level >= 2 else 'badge-danger')
            html += f"""
            <tr>
                <td><span class="badge {badge}">L{level}</span></td>
                <td>{format_size(item.get('size',0))}</td>
                <td class="path">{item.get('path','')}</td>
                <td>{item.get('suggestion','')}</td>
            </tr>
            """
        html += '</tbody></table>'
        return html

    def _render_security_suggestions(self):
        usage = self.disk_usage_percent
        return f"""
        <div>
            当前磁盘使用率 <strong>{usage:.1f}%</strong>，
            {self._get_disk_usage_suggestion(usage)}
        </div>
        """

    def _get_disk_usage_suggestion(self, usage):
        """获取磁盘使用率建议"""
        if usage < 70:
            return '<span class="badge badge-success">使用率正常</span> - 无需立即清理'
        elif usage < 85:
            return '<span class="badge badge-warning">使用率偏高</span> - 建议清理可清理文件'
        else:
            return '<span class="badge badge-danger">使用率过高</span> - 立即清理大文件和重复文件'

