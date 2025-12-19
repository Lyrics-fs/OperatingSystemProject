import curses
import os


def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


class TerminalUI:
    def __init__(self, data):
        self.data = data  # 当前目录数据
        self.root_data = data  # 根数据备份
        self.history = []  # 用于返回上一级
        self.selected_idx = 0
        self.offset = 0  # 滚动偏移量

    def run(self):
        curses.wrapper(self._main_loop)

    def _main_loop(self, stdscr):
        curses.curs_set(0)  # 隐藏光标
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)  # 目录颜色
        curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)  # 大小颜色
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_WHITE)  # 选中行颜色

        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()

            # 1. 绘制标题
            title = f" 磁盘分析: {self.data['path']} (Total: {format_size(self.data['size'])}) "
            stdscr.addstr(0, 0, title, curses.A_BOLD | curses.A_REVERSE)
            stdscr.addstr(1, 0, "-" * (width - 1))

            # 2. 绘制列表
            children = self.data['children']
            max_display = height - 4

            for i in range(max_display):
                idx = i + self.offset
                if idx >= len(children):
                    break

                item = children[idx]
                display_str = f" {item['name']:<40} | {format_size(item['size']):>10}"

                # 截断过长字符串
                if len(display_str) > width - 2:
                    display_str = display_str[:width - 5] + "..."

                if idx == self.selected_idx:
                    stdscr.addstr(i + 2, 1, display_str, curses.color_pair(3))
                else:
                    stdscr.addstr(i + 2, 1, display_str)

            # 3. 底部提示
            help_text = "[Enter] 进入目录  [Backspace] 返回上一级  [q] 退出"
            stdscr.addstr(height - 1, 0, help_text, curses.A_DIM)

            # 4. 键盘事件处理
            key = stdscr.getch()

            if key == ord('q'):
                break
            elif key == curses.KEY_UP and self.selected_idx > 0:
                self.selected_idx -= 1
                if self.selected_idx < self.offset:
                    self.offset -= 1
            elif key == curses.KEY_DOWN and self.selected_idx < len(children) - 1:
                self.selected_idx += 1
                if self.selected_idx >= self.offset + max_display:
                    self.offset += 1
            elif key in [curses.KEY_ENTER, 10, 13]:
                # 进入子目录
                if children:
                    target = children[self.selected_idx]
                    if target['children']:  # 只有有子节点才能进入
                        self.history.append((self.data, self.selected_idx, self.offset))
                        self.data = target
                        self.selected_idx = 0
                        self.offset = 0
            elif key in [curses.KEY_BACKSPACE, 127, ord('b')]:
                # 返回上一级
                if self.history:
                    prev_data, prev_idx, prev_offset = self.history.pop()
                    self.data = prev_data
                    self.selected_idx = prev_idx
                    self.offset = prev_offset