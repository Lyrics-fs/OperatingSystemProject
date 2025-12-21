import os
import time
import random


def format_size(size):
    """格式化文件大小"""
    if size < 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def generate_random_color():
    """生成随机颜色"""
    return f'#{random.randint(0, 0xFFFFFF):06x}'


class EnhancedHTMLReporter:
    def __init__(self, scan_data):
        """
        初始化报告生成器
        :param scan_data: 包含所有扫描信息的字典
        """
        self.data = scan_data
        self.current_time = time.strftime('%Y-%m-%d %H:%M:%S')

    def generate(self, filename="enhanced_disk_report.html"):
        """生成增强版HTML报告"""
        html_content = self._generate_html_content()
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"增强版磁盘报告已生成: {os.path.abspath(filename)}")
        return os.path.abspath(filename)

    def _generate_html_content(self):
        """生成HTML内容"""
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
    <title>磁盘使用分析报告 - {self.data.get('path', '.')}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/jquery@3.6.0/dist/jquery.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Microsoft YaHei', Arial, sans-serif;
        }}
        body {{
            background-color: #f8f9fa;
            color: #333;
            line-height: 1.6;
            padding: 20px;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            padding: 30px;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #e9ecef;
        }}
        .header h1 {{
            color: #2c3e50;
            margin-bottom: 10px;
        }}
        .header .meta {{
            color: #6c757d;
            font-size: 14px;
        }}
        .section {{
            margin-bottom: 40px;
            padding: 20px;
            background: #fafafa;
            border-radius: 8px;
        }}
        .section h2 {{
            color: #007bff;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid #dee2e6;
        }}
        .chart-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            margin-bottom: 30px;
        }}
        .chart-container {{
            flex: 1;
            min-width: 400px;
            height: 400px;
            position: relative;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        th, td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #e9ecef;
        }}
        th {{
            background-color: #007bff;
            color: white;
            font-weight: 600;
        }}
        tr:hover {{
            background-color: #f8f9fa;
        }}
        .tree-view {{
            padding-left: 20px;
            font-family: monospace;
        }}
        .tree-item {{
            margin: 5px 0;
        }}
        .tree-dir {{
            color: #007bff;
            font-weight: 500;
        }}
        .tree-size {{
            color: #6c757d;
            font-size: 12px;
            margin-left: 10px;
        }}
        .badge {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
            margin-left: 8px;
        }}
        .badge-danger {{
            background-color: #dc3545;
            color: white;
        }}
        .badge-warning {{
            background-color: #ffc107;
            color: #212529;
        }}
        .badge-success {{
            background-color: #28a745;
            color: white;
        }}
        .badge-info {{
            background-color: #17a2b8;
            color: white;
        }}
        .progress-bar {{
            height: 8px;
            background-color: #e9ecef;
            border-radius: 4px;
            overflow: hidden;
            margin: 5px 0;
        }}
        .progress-fill {{
            height: 100%;
            background-color: #007bff;
        }}
        .security-level {{
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 5px;
        }}
        .level-1 {{ background-color: #dc3545; }} /* 高风险 */
        .level-2 {{ background-color: #ffc107; }} /* 中风险 */
        .level-3 {{ background-color: #28a745; }} /* 低风险 */
        .level-4 {{ background-color: #17a2b8; }} /* 安全 */
        .expand-btn {{
            background: none;
            border: none;
            color: #007bff;
            cursor: pointer;
            font-size: 16px;
            padding: 0 5px;
        }}
        .hidden {{
            display: none;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- 头部信息 -->
        <div class="header">
            <h1>磁盘使用分析报告</h1>
            <div class="meta">
                扫描路径: {self.data.get('path', '.')} | 
                生成时间: {self.current_time} | 
                总占用空间: <strong>{format_size(self.data.get('total_size', 0))}</strong> |
                当前磁盘使用率: <strong>{self.data.get('disk_usage', 0):.1f}%</strong>
            </div>
        </div>

        <!-- 图表区域 -->
        <div class="chart-row">
            <!-- 文件类型饼图 -->
            <div class="chart-container">
                <canvas id="fileTypeChart"></canvas>
            </div>
            <!-- 历史趋势图 -->
            <div class="chart-container">
                <canvas id="trendChart"></canvas>
            </div>
        </div>

        <!-- 目录树状视图 -->
        <div class="section">
            <h2>目录树状结构</h2>
            <div class="tree-view">
                {dir_tree_html}
            </div>
        </div>

        <!-- 扁平目录统计 -->
        <div class="section">
            <h2>目录大小排行 (Top 50)</h2>
            {flat_dirs_html}
        </div>

        <!-- 重复文件检测 -->
        <div class="section">
            <h2>重复文件检测
                <span class="badge badge-warning">{len(self.data.get('duplicate_files', []))}</span>
            </h2>
            {duplicate_files_html}
        </div>

        <!-- 可清理文件识别 -->
        <div class="section">
            <h2>可清理文件识别
                <span class="badge badge-danger">{format_size(sum(f['size'] for f in self.data.get('cleanable_files', [])))}</span>
            </h2>
            {cleanable_files_html}
        </div>

        <!-- 安全删除建议 -->
        <div class="section">
            <h2>安全删除建议</h2>
            {security_suggestions_html}
        </div>

        <!-- 监控信息 -->
        <div class="section">
            <h2>磁盘使用率监控建议</h2>
            <table>
                <tr>
                    <th>监控项</th>
                    <th>当前值</th>
                    <th>建议阈值</th>
                    <th>操作建议</th>
                </tr>
                <tr>
                    <td>磁盘使用率</td>
                    <td>{self.data.get('disk_usage', 0):.1f}%</td>
                    <td>85%</td>
                    <td>
                        {self._get_disk_usage_suggestion(self.data.get('disk_usage', 0))}
                    </td>
                </tr>
                <tr>
                    <td>可清理空间</td>
                    <td>{format_size(sum(f['size'] for f in self.data.get('cleanable_files', [])))}</td>
                    <td>-</td>
                    <td>清理后可释放上述空间，建议定期清理缓存和日志文件</td>
                </tr>
                <tr>
                    <td>重复文件空间</td>
                    <td>{format_size(sum(sum(f['size'] for f in dup) - dup[0]['size'] for dup in self.data.get('duplicate_files', [])))}</td>
                    <td>-</td>
                    <td>删除重复文件可释放上述空间，建议保留最新版本</td>
                </tr>
            </table>
            <p style="margin-top: 15px; color: #6c757d;">
                <strong>定时监控建议：</strong> 建议每24小时监控一次磁盘使用率，当使用率超过80%时发送告警通知，
                每周生成一次磁盘使用报告，每月进行一次全面清理。
            </p>
        </div>
    </div>

    <script>
        // 文件类型饼图
        const pieCtx = document.getElementById('fileTypeChart').getContext('2d');
        new Chart(pieCtx, {{
            type: 'pie',
            data: {{
                labels: {pie_data['labels']},
                datasets: [{{
                    label: '文件类型占比',
                    data: {pie_data['values']},
                    backgroundColor: {pie_data['colors']},
                    borderWidth: 1
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{
                        position: 'right',
                    }},
                    title: {{
                        display: true,
                        text: '文件类型分布占比'
                    }},
                    tooltip: {{
                        callbacks: {{
                            label: function(context) {{
                                const label = context.label || '';
                                const value = context.raw || 0;
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = ((value / total) * 100).toFixed(1);
                                return `${{label}}: ${{formatSize(value)}} (${{percentage}}%)`;
                            }}
                        }}
                    }}
                }}
            }}
        }});

        // 历史趋势图
        const trendCtx = document.getElementById('trendChart').getContext('2d');
        new Chart(trendCtx, {{
            type: 'line',
            data: {{
                labels: {trend_data['labels']},
                datasets: [{{
                    label: '磁盘使用空间 (GB)',
                    data: {trend_data['values']},
                    borderColor: '#007bff',
                    backgroundColor: 'rgba(0, 123, 255, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.3
                }}, {{
                    label: '使用率 (%)',
                    data: {trend_data['usage_values']},
                    borderColor: '#dc3545',
                    backgroundColor: 'rgba(220, 53, 69, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.3,
                    yAxisID: 'y1'
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    title: {{
                        display: true,
                        text: '磁盘使用历史趋势'
                    }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: true,
                        title: {{
                            display: true,
                            text: '使用空间 (GB)'
                        }}
                    }},
                    y1: {{
                        beginAtZero: true,
                        max: 100,
                        position: 'right',
                        title: {{
                            display: true,
                            text: '使用率 (%)'
                        }},
                        grid: {{
                            drawOnChartArea: false
                        }}
                    }}
                }}
            }}
        }});

        // 格式化文件大小
        function formatSize(size) {{
            if (size < 0) return "0 B";
            const units = ['B', 'KB', 'MB', 'GB', 'TB'];
            let s = size;
            for (let unit of units) {{
                if (s < 1024) {{
                    return s.toFixed(2) + ' ' + unit;
                }}
                s /= 1024;
            }}
            return s.toFixed(2) + ' PB';
        }}

        // 目录树展开/折叠功能
        document.querySelectorAll('.expand-btn').forEach(btn => {{
            btn.addEventListener('click', function() {{
                const targetId = this.getAttribute('data-target');
                const target = document.getElementById(targetId);
                if (target) {{
                    target.classList.toggle('hidden');
                    this.textContent = target.classList.contains('hidden') ? '+' : '-';
                }}
            }});
        }});
    </script>
</body>
</html>
        """

    def _prepare_pie_data(self):
        """准备饼图数据"""
        file_types = self.data.get('file_types', {})
        total_size = sum(file_types.values())
        
        # 过滤小文件类型，合并为"其他"
        filtered_types = {}
        other_size = 0
        min_percentage = 2  # 小于2%的类型合并为其他
        
        for ext, size in file_types.items():
            percentage = (size / total_size) * 100 if total_size > 0 else 0
            if percentage >= min_percentage:
                filtered_types[ext] = size
            else:
                other_size += size
        
        if other_size > 0:
            filtered_types['其他'] = other_size
        
        # 生成颜色
        colors = []
        for _ in filtered_types:
            colors.append(generate_random_color())
        
        return {
            'labels': list(filtered_types.keys()),
            'values': list(filtered_types.values()),
            'colors': colors,
            'total': total_size
        }

    def _prepare_trend_data(self):
        """准备趋势图数据"""
        history = self.data.get('history_data', [])
        
        # 生成模拟数据（如果没有历史数据）
        if not history:
            from datetime import datetime, timedelta
            now = datetime.now()
            history = []
            for i in range(30):
                date = now - timedelta(days=29-i)
                # 模拟数据
                usage = 40 + (i % 10) * 3 + (i // 10) * 2
                size = 200 + i * 2.5
                history.append({
                    'date': date.strftime('%Y-%m-%d'),
                    'usage': usage,
                    'size': size * 1024 * 1024 * 1024  # 转换为字节
                })
        
        labels = [item['date'] for item in history]
        values = [item['size'] / (1024*1024*1024) for item in history]  # 转换为GB
        usage_values = [item['usage'] for item in history]
        
        return {
            'labels': labels,
            'values': values,
            'usage_values': usage_values
        }

    def _render_dir_tree(self, dir_node, level):
        """渲染目录树"""
        if not dir_node:
            return '<div class="tree-item">无数据</div>'
        
        node_id = f"dir_{id(dir_node)}"
        indent = level * 20
        
        html = f'''
        <div class="tree-item" style="margin-left: {indent}px;">
            <button class="expand-btn" data-target="{node_id}">-</button>
            <span class="tree-dir">{dir_node.get('name', '根目录')}</span>
            <span class="tree-size">{format_size(dir_node.get('size', 0))}</span>
            <div class="progress-bar">
                <div class="progress-fill" style="width: {dir_node.get('percentage', 0):.1f}%"></div>
            </div>
            <div id="{node_id}">
        '''
        
        # 渲染子目录
        for child in dir_node.get('children', [])[:10]:  # 限制显示前10个子目录
            if child['children'] is not None:  # 只显示目录
                html += self._render_dir_tree(child, level + 1)
        
        html += '</div></div>'
        return html

    def _render_flat_dirs(self):
        """渲染扁平目录列表"""
        flat_dirs = self.data.get('flat_dirs', [])[:50]  # Top 50
        
        if not flat_dirs:
            return '<div>无目录数据</div>'
        
        html = '<table><thead><tr><th>目录路径</th><th>大小</th><th>占比</th></tr></thead><tbody>'
        
        for dir_info in flat_dirs:
            percentage = dir_info.get('percentage', 0)
            html += f'''
            <tr>
                <td>{dir_info.get('path', '')}</td>
                <td>{format_size(dir_info.get('size', 0))}</td>
                <td>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: {percentage:.1f}%"></div>
                    </div>
                    <small>{percentage:.1f}%</small>
                </td>
            </tr>
            '''
        
        html += '</tbody></table>'
        return html

    def _render_duplicate_files(self):
        """渲染重复文件列表"""
        duplicates = self.data.get('duplicate_files', [])
        
        if not duplicates:
            return '<div>未检测到重复文件</div>'
        
        html = '<table><thead><tr><th>文件大小</th><th>重复数量</th><th>文件路径</th></tr></thead><tbody>'
        
        for dup_group in duplicates:
            if not dup_group:
                continue
            
            size = dup_group[0]['size']
            count = len(dup_group)
            
            # 第一个文件
            html += f'''
            <tr style="background-color: #f8f9fa;">
                <td rowspan="{count}">{format_size(size)}</td>
                <td rowspan="{count}">{count}</td>
                <td>{dup_group[0]['path']}</td>
            </tr>
            '''
            
            # 其他重复文件
            for file in dup_group[1:]:
                html += f'<tr><td style="color: #6c757d;">{file["path"]}</td></tr>'
        
        html += '</tbody></table>'
        return html

    def _render_cleanable_files(self):
        """渲染可清理文件列表"""
        cleanable = self.data.get('cleanable_files', [])
        
        if not cleanable:
            return '<div>未识别到可清理文件</div>'
        
        # 按类型分组
        by_type = {}
        for file in cleanable:
            file_type = file.get('type', '其他')
            if file_type not in by_type:
                by_type[file_type] = []
            by_type[file_type].append(file)
        
        html = '<table><thead><tr><th>文件类型</th><th>文件路径</th><th>大小</th><th>清理建议</th></tr></thead><tbody>'
        
        for file_type, files in by_type.items():
            # 类型标题行
            total_size = sum(f['size'] for f in files)
            html += f'''
            <tr style="background-color: #e9ecef;">
                <td>
                    {file_type} 
                    <span class="badge badge-danger">{len(files)}个文件</span>
                </td>
                <td colspan="2"><strong>总计: {format_size(total_size)}</strong></td>
                <td>{self._get_clean_suggestion(file_type)}</td>
            </tr>
            '''
            
            # 文件列表
            for file in files[:20]:  # 每个类型显示前20个
                html += f'''
                <tr>
                    <td></td>
                    <td>{file['path']}</td>
                    <td>{format_size(file['size'])}</td>
                    <td>
                        <span class="badge badge-warning">建议清理</span>
                    </td>
                </tr>
                '''
        
        html += '</tbody></table>'
        return html

    def _render_security_suggestions(self):
        """渲染安全删除建议"""
        suggestions = self.data.get('security_suggestions', [])
        
        if not suggestions:
            return '<div>暂无删除建议</div>'
        
        html = '<table><thead><tr><th>安全等级</th><th>文件路径</th><th>大小</th><th>白名单</th><th>删除建议</th></tr></thead><tbody>'
        
        for item in suggestions:
            level = item.get('security_level', 4)
            whitelist = item.get('whitelist', False)
            
            html += f'''
            <tr>
                <td>
                    <span class="security-level level-{level}"></span>
                    {self._get_level_text(level)}
                </td>
                <td>{item['path']}</td>
                <td>{format_size(item['size'])}</td>
                <td>{'✓' if whitelist else '×'}</td>
                <td>{item['suggestion']}</td>
            </tr>
            '''
        
        html += '</tbody></table>'
        
        # 添加白名单说明
        html += '''
        <div style="margin-top: 15px; padding: 10px; background: #e9ecef; border-radius: 5px;">
            <strong>安全等级说明：</strong><br>
            <span class="security-level level-1"></span> 高风险 - 不建议删除 | 
            <span class="security-level level-2"></span> 中风险 - 谨慎删除 | 
            <span class="security-level level-3"></span> 低风险 - 可安全删除 | 
            <span class="security-level level-4"></span> 安全 - 完全可删除
        </div>
        '''
        
        return html

    def _get_level_text(self, level):
        """获取安全等级文本"""
        levels = {
            1: '高风险',
            2: '中风险',
            3: '低风险',
            4: '安全'
        }
        return levels.get(level, '未知')

    def _get_clean_suggestion(self, file_type):
        """获取文件清理建议"""
        type_lower = file_type.lower()
        if '缓存' in file_type or 'cache' in type_lower:
            return '缓存文件可安全删除，程序会重新生成'
        elif '日志' in file_type or 'log' in type_lower:
            return '日志文件可删除，建议保留最近7天的日志'
        elif '临时' in file_type or 'temp' in type_lower:
            return '临时文件完全可删除，无任何风险'
        elif '下载' in file_type or 'download' in type_lower:
            return '下载文件请手动确认后删除'
        else:
            return '请确认文件无用后再删除'

    def _get_disk_usage_suggestion(self, usage):
        """获取磁盘使用率建议"""
        if usage < 70:
            return '<span class="badge badge-success">使用率正常</span> - 无需立即清理'
        elif usage < 85:
            return '<span class="badge badge-warning">使用率偏高</span> - 建议清理可清理文件'
        else:
            return '<span class="badge badge-danger">使用率过高</span> - 立即清理大文件和重复文件'

