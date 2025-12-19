import os
import time


def format_size(size):
    # 简单的 size 格式化复用
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
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>磁盘使用分析报告</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; background: #f4f4f4; }}
                .container {{ max-width: 1000px; margin: 0 auto; background: white; padding: 20px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
                h1, h2 {{ color: #333; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
                table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
                th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #007bff; color: white; }}
                tr:hover {{ background-color: #f1f1f1; }}
                .bar-container {{ background-color: #e0e0e0; width: 100px; height: 10px; border-radius: 5px; }}
                .bar {{ background-color: #28a745; height: 100%; border-radius: 5px; }}
                .warning {{ color: red; font-weight: bold; }}
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

                <h2>文件类型统计 (Top 10)</h2>
                <table>
                    <thead><tr><th>类型</th><th>总大小</th></tr></thead>
                    <tbody>
                        {self._render_type_rows(self.summary['file_types'][:10])}
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
        </body>
        </html>
        """

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"报告已生成: {os.path.abspath(filename)}")

    def _render_dir_rows(self, children, total_size):
        rows = ""
        for child in children[:10]:  # 只显示前10个目录
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

    def _render_type_rows(self, types):
        rows = ""
        for ext, size in types:
            rows += f"<tr><td>{ext}</td><td>{format_size(size)}</td></tr>"
        return rows

    def _render_file_rows(self, files):
        rows = ""
        for size, path in files:
            rows += f"<tr><td>{path}</td><td class='warning'>{format_size(size)}</td></tr>"
        return rows