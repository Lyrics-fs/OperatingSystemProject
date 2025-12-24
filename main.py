import argparse
import os
import sys
import threading
import time
import select
import termios
import tty

from analyzer import DiskAnalyzer
from tui import TerminalUI, format_size
from reporter import EnhancedHTMLReporter


class _RawStdin:
    def __init__(self):
        self.fd = sys.stdin.fileno()
        self._old = None

    def __enter__(self):
        if not sys.stdin.isatty():
            return self
        self._old = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._old is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self._old)


def _read_key_nonblocking():
    if not sys.stdin.isatty():
        return None
    r, _, _ = select.select([sys.stdin], [], [], 0)
    if r:
        try:
            return sys.stdin.read(1)
        except Exception:
            return None
    return None


def _terminal_width(default=120):
    try:
        return os.get_terminal_size().columns
    except OSError:
        return default


def _print_scan_progress_line(stats, stopped=False):
    cur = stats.get("current_path") or ""
    term_width = _terminal_width()

    left = f"Scanning...  files={stats.get('scanned_files', 0)}  size={format_size(stats.get('scanned_bytes', 0))}"
    hint = "  [q] stop" if not stopped else "  stopping..."

    # 预留：至少要能显示 current=
    max_cur = max(10, term_width - len(left) - len("  current=") - len(hint) - 1)
    if len(cur) > max_cur:
        cur = "…" + cur[-(max_cur - 1):]

    line = f"{left}  current={cur}{hint}"

    # ✅ 防止换行导致“输出粘连”：强制截断
    if len(line) >= term_width:
        line = line[: max(0, term_width - 1)]

    # ✅ ANSI 清行 + 回到行首
    sys.stdout.write("\r\033[2K" + line)
    sys.stdout.flush()


def run_scan_with_live_progress(path, depth):
    analyzer = DiskAnalyzer(path, max_depth=depth)

    stop_event = threading.Event()
    latest_stats = {
        "scanned_files": 0,
        "scanned_bytes": 0,
        "current_path": os.path.abspath(path),
    }
    lock = threading.Lock()

    def on_progress(stats):
        with lock:
            latest_stats.update(stats)

    result_holder = {"tree": None, "error": None}

    def worker():
        try:
            result_holder["tree"] = analyzer.scan(on_progress=on_progress, stop_event=stop_event)
        except Exception as e:
            result_holder["error"] = e

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    with _RawStdin():
        last_draw = 0.0
        while t.is_alive():
            now = time.time()
            if now - last_draw >= 0.15:  # ✅ 降低刷新频率，减少刷屏
                with lock:
                    stats = dict(latest_stats)
                _print_scan_progress_line(stats, stopped=stop_event.is_set())
                last_draw = now

            k = _read_key_nonblocking()
            if k in ("q", "Q"):
                stop_event.set()

            time.sleep(0.03)

    with lock:
        stats = dict(latest_stats)
    _print_scan_progress_line(stats, stopped=stop_event.is_set())
    sys.stdout.write("\n")
    sys.stdout.flush()

    if result_holder["error"] is not None:
        raise result_holder["error"]

    return analyzer, result_holder["tree"], stop_event.is_set()


def monitor_disk(path, interval_sec=2.0):
    target = os.path.abspath(path)

    def _usage():
        st = os.statvfs(target)
        total = st.f_frsize * st.f_blocks
        free = st.f_frsize * st.f_bfree
        avail = st.f_frsize * st.f_bavail
        used = total - free
        used_pct = (used / total * 100.0) if total else 0.0
        return total, used, avail, used_pct

    last = None
    with _RawStdin():
        while True:
            total, used, avail, used_pct = _usage()
            delta = ""
            if last is not None:
                du = used - last[1]
                if du != 0:
                    sign = "+" if du > 0 else ""
                    delta = f"  used_delta={sign}{format_size(abs(du))}"
            last = (total, used, avail, used_pct)

            line = (
                f"Monitoring...  path={target}  "
                f"used={format_size(used)}/{format_size(total)} ({used_pct:.1f}%)  "
                f"avail={format_size(avail)}{delta}  [q] quit"
            )
            term_width = _terminal_width()
            if len(line) >= term_width:
                line = line[: max(0, term_width - 1)]

            sys.stdout.write("\r\033[2K" + line)
            sys.stdout.flush()

            end = time.time() + interval_sec
            while time.time() < end:
                k = _read_key_nonblocking()
                if k in ("q", "Q"):
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    return
                time.sleep(0.05)


def main():
    parser = argparse.ArgumentParser(description="Linux 磁盘使用分析与管理工具")
    parser.add_argument("path", nargs="?", default=".", help="要扫描的目录路径 (默认: 当前目录)")
    parser.add_argument("--depth", type=int, default=2, help="目录扫描深度 (默认: 2)")
    parser.add_argument("--report", action="store_true", help="生成 HTML 报告而不启动 UI")
    parser.add_argument("--enhanced", action="store_true", help="生成增强版 HTML 报告")
    parser.add_argument("--tui", action="store_true", help="扫描完成后进入 TUI（目录树浏览）")
    parser.add_argument("--monitor", action="store_true", help="扫描完成后进入实时监测（默认行为）")
    parser.add_argument("--interval", type=float, default=2.0, help="监控刷新间隔秒数 (默认: 2.0)")
    args = parser.parse_args()

    scan_path = args.path
    if not os.path.exists(scan_path):
        print(f"路径不存在: {scan_path}")
        sys.exit(1)

    analyzer, tree_data, stopped = run_scan_with_live_progress(scan_path, args.depth)

    if stopped:
        print("扫描已停止（按 q）。结果可能不完整。")

    if args.report or args.enhanced:
        summary_data = analyzer.get_enhanced_summary(tree_data)
        reporter = EnhancedHTMLReporter(summary_data)
        out = "enhanced_disk_report.html" if args.enhanced else "disk_report.html"
        reporter.generate(out)
        print(f"已生成报告: {out}")
        return

    if args.tui and tree_data is not None:
        try:
            ui = TerminalUI(tree_data)
            ui.run()
        except Exception as e:
            print(f"UI 运行出错 (可能是屏幕太小): {e}")
        return

    print("扫描完成，现在进入实时监测")
    monitor_disk(scan_path, interval_sec=args.interval)


if __name__ == "__main__":
    main()

