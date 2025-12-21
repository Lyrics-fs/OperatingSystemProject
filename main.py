import argparse
import sys
import os
from analyzer import DiskAnalyzer
from tui import TerminalUI
from reporter import EnhancedHTMLReporter


def main():
    parser = argparse.ArgumentParser(description="Linux 磁盘使用分析与管理工具")
    parser.add_argument("path", nargs="?", default=".", help="要扫描的目录路径 (默认: 当前目录)")
    parser.add_argument("--report", action="store_true", help="生成 HTML 报告而不启动 UI")
    parser.add_argument("--depth", type=int, default=2, help="目录扫描深度 (默认: 2)")
    parser.add_argument("--enhanced", action="store_true", help="生成增强版 HTML 报告")

    args = parser.parse_args()

    target_path = args.path
    if not os.path.exists(target_path):
        print(f"错误: 路径 '{target_path}' 不存在")
        sys.exit(1)

    print(f"正在扫描 '{target_path}'，请稍候...")

    # 1. 执行分析
    analyzer = DiskAnalyzer(target_path, max_depth=args.depth)
    tree_data = analyzer.scan()
    
    # 2. 根据模式输出
    if args.report or args.enhanced:
        # 生成 HTML 报告
        summary_data = analyzer.get_enhanced_summary(tree_data['size'])
        reporter = EnhancedHTMLReporter(summary_data)
        reporter.generate("enhanced_disk_report.html")
    else:
        # 启动 TUI 界面
        try:
            ui = TerminalUI(tree_data)
            ui.run()
        except Exception as e:
            print(f"UI 运行出错 (可能是屏幕太小): {e}")


if __name__ == "__main__":
    main()

