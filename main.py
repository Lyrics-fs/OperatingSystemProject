import argparse
import os
import sys
import threading
import time
from datetime import datetime

from analyzer import DiskAnalyzer
from reporter import EnhancedHTMLReporter

# 尝试导入TUI相关模块，如果失败则提供降级方案
try:
    from tui import TerminalUI, format_size

    TUI_AVAILABLE = True
except ImportError as e:
    print(f"[警告] TUI模块导入失败: {e}")
    TUI_AVAILABLE = False


    # 提供简单的format_size函数
    def format_size(size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"


# 跨平台输入处理
class _RawStdin:
    """跨平台原始输入处理"""

    def __init__(self):
        self._original_settings = None

    def __enter__(self):
        if not sys.stdin.isatty():
            return self

        if os.name == 'posix':  # Linux/Mac
            import termios
            import tty
            self.fd = sys.stdin.fileno()
            self._original_settings = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
        elif os.name == 'nt':  # Windows
            import msvcrt
            # Windows控制台已经支持非阻塞读取

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._original_settings is not None and os.name == 'posix':
            import termios
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self._original_settings)


# 跨平台非阻塞键盘读取
def _read_key_nonblocking():
    """跨平台非阻塞键盘读取"""
    if not sys.stdin.isatty():
        return None

    try:
        if os.name == 'posix':  # Linux/Mac
            import select
            rlist, _, _ = select.select([sys.stdin], [], [], 0)
            if rlist:
                return sys.stdin.read(1)
        elif os.name == 'nt':  # Windows
            import msvcrt
            if msvcrt.kbhit():
                return msvcrt.getch().decode('utf-8', errors='ignore')
    except:
        pass

    return None


def _terminal_width(default=80):
    """获取终端宽度"""
    try:
        return os.get_terminal_size().columns
    except:
        return default


def _print_scan_progress_line(stats, stopped=False):
    """打印扫描进度行"""
    cur = stats.get("current_path") or ""
    term_width = _terminal_width()

    left = f"扫描中... 文件数={stats.get('scanned_files', 0)}  大小={format_size(stats.get('scanned_bytes', 0))}"
    hint = "  [q] 停止" if not stopped else "  正在停止..."

    # 计算可用空间
    max_cur = max(10, term_width - len(left) - len("  当前路径=") - len(hint) - 1)
    if len(cur) > max_cur:
        cur = "…" + cur[-(max_cur - 1):]

    line = f"{left}  当前路径={cur}{hint}"

    # 防止换行
    if len(line) >= term_width:
        line = line[:max(0, term_width - 1)]

    # 清行并输出
    sys.stdout.write("\r\033[2K" + line)
    sys.stdout.flush()


def run_scan_with_live_progress(path, depth, method='auto', workers=4, use_cache=True):
    """
    带实时进度条的扫描

    Args:
        path: 扫描路径
        depth: 扫描深度
        method: 扫描方法
        workers: 工作线程数
        use_cache: 是否使用缓存
    """
    print(f"[准备] 开始扫描: {os.path.abspath(path)}")
    print(f"[配置] 方法: {method}, 深度: {depth}, 线程: {workers}")

    analyzer = DiskAnalyzer(
        path,
        max_depth=depth,
        scan_method=method,
        num_workers=workers,
        use_cache=use_cache,
        ignore_errors=True
    )

    stop_event = threading.Event()
    latest_stats = {
        "scanned_files": 0,
        "scanned_bytes": 0,
        "current_path": os.path.abspath(path),
    }
    lock = threading.Lock()

    def on_progress(stats):
        """进度回调函数"""
        with lock:
            latest_stats.update(stats)

    result_holder = {"tree": None, "error": None}

    def worker():
        """扫描工作线程"""
        try:
            print("[扫描] 启动扫描线程...")
            result_holder["tree"] = analyzer.scan(on_progress=on_progress, stop_event=stop_event)
        except Exception as e:
            result_holder["error"] = e
            import traceback
            traceback.print_exc()

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    with _RawStdin():
        last_draw = 0.0
        print("[进度] 开始显示进度...")

        while t.is_alive():
            now = time.time()
            if now - last_draw >= 0.2:  # 降低刷新频率
                with lock:
                    stats = dict(latest_stats)
                _print_scan_progress_line(stats, stopped=stop_event.is_set())
                last_draw = now

            # 检查键盘输入
            key = _read_key_nonblocking()
            if key and key.lower() == 'q':
                print("\n[操作] 用户请求停止扫描...")
                stop_event.set()

            time.sleep(0.05)  # 降低CPU使用率

    # 最终更新显示
    with lock:
        stats = dict(latest_stats)
    _print_scan_progress_line(stats, stopped=stop_event.is_set())
    sys.stdout.write("\n")
    sys.stdout.flush()

    if result_holder["error"] is not None:
        raise result_holder["error"]

    print(f"[完成] 扫描结束，文件数: {stats['scanned_files']}")
    return analyzer, result_holder["tree"], stop_event.is_set()


def get_enhanced_summary_safe(analyzer, tree_data):
    """
    安全地获取增强摘要

    兼容analyzer
    """

    if isinstance(tree_data, dict) and 'total_size' in tree_data:
        print("[信息] 使用scan()返回的完整数据")
        return tree_data

    # 尝试调用get_enhanced_summary方法
    if hasattr(analyzer, 'get_enhanced_summary'):
        try:
            print("[信息] 调用get_enhanced_summary()")
            return analyzer.get_enhanced_summary(tree_data.get('size', 0))
        except Exception as e:
            print(f"[警告] get_enhanced_summary失败: {e}")

    # 降级处理
    print("[信息] 使用基础数据")
    return {
        'path': tree_data.get('path', '.'),
        'total_size': tree_data.get('size', 0),
        'dir_tree': tree_data,
        'flat_dirs': [],
        'file_types': {},
        'duplicate_files': {},
        'cleanable_files': [],
        'security_suggestions': [],
        'history_data': [],
        'disk_usage': 0,
        'scan_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }


def monitor_disk_simple(path, interval_sec=5.0):
    """简化的磁盘监控（跨平台）"""
    target = os.path.abspath(path)
    print(f"[监控] 开始监控: {target}")
    print("[提示] 按 'q' 键退出监控")

    def _get_disk_usage():
        """获取磁盘使用率"""
        try:
            # 使用analyzer的方法
            analyzer = DiskAnalyzer(target, max_depth=1, use_cache=False)
            return analyzer._get_disk_usage()
        except:
            return 50.0  # 默认值

    with _RawStdin():
        try:
            while True:
                usage = _get_disk_usage()
                line = f"磁盘监控: {target}  使用率: {usage:.1f}%  [按q退出]"

                # 清行并输出
                sys.stdout.write("\r\033[2K" + line)
                sys.stdout.flush()

                # 检查退出
                key = _read_key_nonblocking()
                if key and key.lower() == 'q':
                    print("\n[监控] 退出监控模式")
                    break

                time.sleep(interval_sec)

        except KeyboardInterrupt:
            print("\n[监控] 监控被中断")
        except Exception as e:
            print(f"\n[监控] 错误: {e}")


def prepare_tui_data(tree_data, target_path):
    """准备TUI界面所需的数据格式"""
    if not TUI_AVAILABLE:
        print("[错误] TUI模块不可用")
        return None

    # 检查数据格式
    if isinstance(tree_data, dict) and 'dir_tree' in tree_data:
        dir_tree = tree_data.get('dir_tree', {})
        tui_data = {
            'path': tree_data.get('path', target_path),
            'size': tree_data.get('total_size', 0),
            'children': dir_tree.get('children', [])
        }
    else:
        tui_data = {
            'path': tree_data.get('path', target_path),
            'size': tree_data.get('size', 0),
            'children': []
        }

        if 'children' in tree_data:
            for child in tree_data['children']:
                if child.get('children') is not None:
                    tui_data['children'].append({
                        'path': child.get('path', ''),
                        'name': child.get('name', ''),
                        'size': child.get('size', 0),
                        'children': child.get('children', [])
                    })

    return tui_data


def print_usage_summary(result):
    """打印使用情况摘要"""
    if not result:
        return

    print("\n" + "=" * 60)
    print("扫描结果摘要")
    print("=" * 60)

    total_gb = result.get('total_size', 0) / (1024 ** 3)
    print(f"总大小: {total_gb:.2f} GB ({format_size(result.get('total_size', 0))})")

    if 'file_types' in result:
        print(f"文件类型数: {len(result['file_types'])}")

    if 'cleanable_files' in result:
        cleanable_size = sum(f['size'] for f in result['cleanable_files'])
        print(f"可清理文件: {len(result['cleanable_files'])} 个, 大小: {format_size(cleanable_size)}")

    if 'disk_usage' in result:
        print(f"磁盘使用率: {result['disk_usage']:.1f}%")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="跨平台磁盘使用分析工具")
    parser.add_argument("path", nargs="?", default=".", help="要扫描的目录路径 (默认: 当前目录)")
    parser.add_argument("--depth", type=int, default=3, help="目录扫描深度 (默认: 3)")
    parser.add_argument("--report", action="store_true", help="生成 HTML 报告")
    parser.add_argument("--enhanced", action="store_true", help="生成增强版 HTML 报告")
    parser.add_argument("--tui", action="store_true", help="扫描完成后进入 TUI 浏览")
    parser.add_argument("--monitor", action="store_true", help="扫描完成后进入实时监控")
    parser.add_argument("--interval", type=float, default=5.0, help="监控刷新间隔秒数")

    # 扫描参数
    parser.add_argument("--method",
                        choices=['auto', 'fastfind', 'fastwalk', 'walk', 'du', 'hybrid', 'simple'],
                        default='auto',
                        help="扫描方法 (默认: auto)")
    parser.add_argument("--workers", type=int, default=4,
                        help="并行工作线程数 (默认: 4)")
    parser.add_argument("--no-cache", action="store_true",
                        help="禁用缓存")
    parser.add_argument("--fast", action="store_true",
                        help="快速模式")
    parser.add_argument("--quiet", action="store_true",
                        help="安静模式，减少输出")

    args = parser.parse_args()

    # 设置路径
    scan_path = os.path.abspath(args.path)
    if not os.path.exists(scan_path):
        print(f"[错误] 路径不存在: {scan_path}")
        sys.exit(1)

    # 平台适配
    if os.name == 'nt':
        print(f"[系统] Windows 系统")
        if args.method == 'fastfind':
            print("[适配] Windows不支持fastfind，自动切换到fastwalk")
            scan_method = 'fastwalk'
        else:
            scan_method = args.method
    else:
        print(f"[系统] Unix/Linux 系统")
        scan_method = args.method

    # 快速模式
    if args.fast:
        if os.name == 'nt':
            scan_method = 'simple'
        else:
            scan_method = 'du'
        print(f"[模式] 快速模式，使用 {scan_method} 方法")

    # 安静模式
    if args.quiet:
        print("[模式] 安静模式，减少输出")

    print(f"[开始] 扫描路径: {scan_path}")

    try:
        # 执行扫描（带进度条）
        analyzer, tree_data, stopped = run_scan_with_live_progress(
            scan_path,
            args.depth,
            method=scan_method,
            workers=args.workers,
            use_cache=not args.no_cache
        )

        if stopped:
            print("[提示] 扫描被用户停止，结果可能不完整")

        # 生成报告
        if args.report or args.enhanced:
            print("[报告] 正在生成HTML报告...")
            summary_data = get_enhanced_summary_safe(analyzer, tree_data)
            reporter = EnhancedHTMLReporter(summary_data)

            if args.enhanced:
                report_name = "enhanced_disk_report.html"
            else:
                report_name = "disk_report.html"

            try:
                report_path = reporter.generate(report_name)
                print(f"[报告] 已生成: {report_path}")

                # 尝试在浏览器中打开
                try:
                    import webbrowser
                    webbrowser.open(f"file://{report_path}")
                    print("[报告] 已在浏览器中打开")
                except:
                    pass

            except Exception as e:
                print(f"[错误] 报告生成失败: {e}")
                import traceback
                traceback.print_exc()

            # 打印摘要
            if not args.quiet:
                print_usage_summary(summary_data)

            return

        # TUI模式
        if args.tui:
            if not TUI_AVAILABLE:
                print("[错误] TUI模块不可用，无法进入TUI模式")
                print("[提示] 请确保tui.py文件存在且没有语法错误")
                sys.exit(1)

            try:
                print("[TUI] 准备进入终端界面...")
                tui_data = prepare_tui_data(tree_data, scan_path)
                if tui_data:
                    ui = TerminalUI(tui_data)
                    ui.run()
                else:
                    print("[错误] 无法准备TUI数据")
            except Exception as e:
                print(f"[错误] TUI运行失败: {e}")
                import traceback
                traceback.print_exc()

            return

        # 监控模式
        if args.monitor:
            print("[监控] 进入磁盘监控模式")
            monitor_disk_simple(scan_path, interval_sec=args.interval)
            return

        # 默认：打印摘要
        if not args.quiet:
            summary_data = get_enhanced_summary_safe(analyzer, tree_data)
            print_usage_summary(summary_data)
            print("\n[提示] 可用选项:")
            print("  --report       生成HTML报告")
            print("  --enhanced     生成增强报告")
            if TUI_AVAILABLE:
                print("  --tui          进入TUI浏览模式")
            print("  --monitor      进入磁盘监控")
            print("  --method=METHOD 选择扫描方法")

    except KeyboardInterrupt:
        print("\n[中断] 程序被用户中断")
    except Exception as e:
        print(f"[错误] 程序执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # 添加简单的帮助提示
    if len(sys.argv) == 2 and sys.argv[1] in ['-h', '--help', 'help']:
        print("磁盘分析工具 - 使用说明")
        print("=" * 50)
        print("基本用法:")
        print("  python main.py .                    # 扫描当前目录")
        print("  python main.py C:\\                 # 扫描C盘")
        print("  python main.py /home/user           # 扫描用户目录")
        print("\n常用选项:")
        print("  --enhanced         生成增强版HTML报告")
        print("  --tui              进入终端交互界面")
        print("  --monitor          监控磁盘使用情况")
        print("  --method=fastwalk  使用快速扫描方法")
        print("  --workers=8        使用8个线程")
        print("  --depth=3          扫描深度3层")
        print("\n示例:")
        print("  python main.py . --enhanced")
        print("  python main.py C:\\ --method=fastwalk --workers=8")
        print("=" * 50)
        sys.exit(0)

    main()
