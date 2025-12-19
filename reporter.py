import os
import time


def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


class HTMLReporter:
    def __init__(self, tree_data, summary_data):
        self.tree = tree_data
        self.summary = summary_data

    def generate(self, filename="report.html"):
        pie_data = self._prepare_pie_data()

        js_format_size = """
        function formatSize(size) {
            const units = ['B', 'KB', 'MB', 'GB', 'TB'];
            let s = size;
            for (let unit of units) {
                if (s < 1024) {
                    return s.toFixed(2) + ' ' + unit;
                }
                s /= 1024;
            }
            return s.toFixed(2) + ' PB';
        }
        """
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>磁盘使用分析报告</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; background: #f4f4f4; }}
                .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
                h1, h2 {{ color: #333; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
                table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
                th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #007bff; color: white; }}
                tr:hover {{ background-color: #f1f1f1; }}
                .bar-container {{ background-color: #e0e0e0; width: 100px; height: 10px; border-radius: 5px; }}
                .bar {{ background-color: #28a745; height: 100%; border-radius: 5px; }}
                .warning {{ color: red; font-weight: bold; }}
                .chart-container {{ display: flex; justify-content: center; margin: 30px 0; }}
                .pie-chart {{ width: 600px; height: 400px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>磁盘使用分析报告</h1>
                <p>扫描路径: {self.tree['path']}</p>
                <p>生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>总大小: <strong>{format_size(self.tree['size'])}</strong></p>

                <h2>顶级目录概览</h2>
                <table>
                    <thead><tr><th>目录名称</th><th>大小</th><th>占比</th></tr></thead>
                    <tbody>
                        {self._render_dir_rows(self.tree['children'], self.tree['size'])}
                    </tbody>
                </table>

                <h2>文件类型分布</h2>
                <div class="chart-container">
                    <canvas id="fileTypePieChart" class="pie-chart"></canvas>
                </div>
                <table>
                    <thead><tr><th>类型</th><th>总大小</th><th>占比</th></tr></thead>
                    <tbody>
                        {self._render_type_rows_with_percent()}
                    </tbody>
                </table>

                <h2>Top 20 大文件</h2>
                <table>
                    <thead><tr><th>文件路径</th><th>大小</th></tr></thead>
                    <tbody>
                        {self._render_file_rows(self.summary['top_files'])}
                    </tbody>
                </table>
            </div>

            <script>
                // JS版本的文件大小格式化函数
                {js_format_size}
                
                // 初始化饼图
                const ctx = document.getElementById('fileTypePieChart').getContext('2d');
                new Chart(ctx, {{
                    type: 'pie',
                    data: {{
                        labels: {pie_data['labels']},
                        datasets: [{{
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
                                text: '文件类型占比分布'
                            }},
                            tooltip: {{
                                callbacks: {{
                                    label: function(context) {{
                                        const label = context.label || '';
                                        const value = context.raw || 0;
                                        const percentage = ((value / {pie_data['total']}) * 100).toFixed(1);
                                        return label + ': ' + formatSize(value) + ' (' + percentage + '%)';
                                    }}
                                }}
                            }}
                        }}
                    }}
                }});
            </script>
        </body>
        </html>
        """

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"报告已生成: {os.path.abspath(filename)}")

    def _prepare_pie_data(self):
        """准备饼图所需的数据"""
        total_size = sum(size for _, size in self.summary['file_types']) if self.summary.get('file_types') else 0
        
        major_types = []
        other_size = 0
        min_percentage = 3 
        
        if self.summary.get('file_types') and total_size > 0:
            for ext, size in self.summary['file_types']:
                percentage = (size / total_size) * 100
                if percentage >= min_percentage:
                    major_types.append((ext, size))
                else:
                    other_size += size
        
        if other_size > 0:
            major_types.append(("其他", other_size))
        
        if not major_types:
            major_types.append(("无数据", 0))
        
        colors = [
            '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', 
            '#FF9F40', '#C9CBCF', '#6B8E23', '#8B4513', '#800080',
            '#00CED1', '#FF6347', '#20B2AA', '#DAA520', '#9370DB'
        ]
        
        while len(colors) < len(major_types):
            colors.extend(colors) 
        
        return {
            'labels': [ext for ext, _ in major_types],
            'values': [size for _, size in major_types],
            'colors': colors[:len(major_types)],
            'total': total_size
        }

    def _render_dir_rows(self, children, total_size):
        rows = ""
        if not children:
            return "<tr><td colspan='3'>无数据</td></tr>"
        
        for child in children[:10]:
            percent = (child['size'] / total_size) * 100 if total_size > 0 else 0
            rows += f"""
            <tr>
                <td>{child['name']}</td>
                <td>{format_size(child['size'])}</td>
                <td>
                    <div style="display:flex; align-items:center;">
                        <span style="width:40px">{percent:.1f}%</span>
                        <div class="bar-container" style="width:100px">
                            <div class="bar" style="width:{percent}%"></div>
                        </div>
                    </div>
                </td>
            </tr>
            """
        return rows

    def _render_type_rows_with_percent(self):
        """带百分比的文件类型统计行"""
        total_size = sum(size for _, size in self.summary['file_types']) if self.summary.get('file_types') else 0
        rows = ""
        
        if not self.summary.get('file_types'):
            return "<tr><td colspan='3'>无数据</td></tr>"
        
        for ext, size in self.summary['file_types'][:10]:
            percent = (size / total_size) * 100 if total_size > 0 else 0
            rows += f"""
            <tr>
                <td>{ext}</td>
                <td>{format_size(size)}</td>
                <td>{percent:.1f}%</td>
            </tr>
            """
        return rows

    def _render_file_rows(self, files):
        rows = ""
        if not files:
            return "<tr><td colspan='2'>无数据</td></tr>"
        
        for size, path in files:
            rows += f"<tr><td>{path}</td><td class='warning'>{format_size(size)}</td></tr>"
        return rows