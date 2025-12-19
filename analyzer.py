import os
import collections


class DiskAnalyzer:
    def __init__(self, root_path, max_depth=2):
        self.root_path = os.path.abspath(root_path)
        self.max_depth = max_depth
        self.file_types = collections.defaultdict(int)  # 扩展名统计
        self.top_files = []  # 存储 (size, path)
        self.top_n_limit = 20

    def scan(self):
        """执行扫描并返回目录树结构"""
        return self._scan_recursive(self.root_path, 0)

    def _scan_recursive(self, current_path, current_depth):
        dir_stat = {
            'path': current_path,
            'name': os.path.basename(current_path) or current_path,
            'size': 0,
            'children': []
        }

        try:
            # 使用 scandir 提高性能
            with os.scandir(current_path) as it:
                for entry in it:
                    if entry.is_symlink():
                        continue

                    if entry.is_file():
                        try:
                            size = entry.stat().st_size
                            dir_stat['size'] += size

                            # 统计文件类型
                            ext = os.path.splitext(entry.name)[1].lower() or "No Ext"
                            self.file_types[ext] += size

                            # 维护 Top-N 大文件
                            self._update_top_files(entry.path, size)
                        except (PermissionError, OSError):
                            pass

                    elif entry.is_dir():
                        if current_depth < self.max_depth:
                            # 递归处理子目录
                            child_stat = self._scan_recursive(entry.path, current_depth + 1)
                            dir_stat['size'] += child_stat['size']
                            dir_stat['children'].append(child_stat)
                        else:
                            # 超过深度的目录，只计算大小不记录子节点
                            size = self._get_deep_size(entry.path)
                            dir_stat['size'] += size
                            # 添加一个简化的子节点记录
                            dir_stat['children'].append({
                                'path': entry.path,
                                'name': entry.name,
                                'size': size,
                                'children': []
                            })

            # 按大小对子目录排序
            dir_stat['children'].sort(key=lambda x: x['size'], reverse=True)
            return dir_stat

        except PermissionError:
            return dir_stat

    def _get_deep_size(self, path):
        """快速获取深度目录大小（不记录详细结构）"""
        total = 0
        try:
            for root, _, files in os.walk(path):
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(root, f))
                    except:
                        pass
        except:
            pass
        return total

    def _update_top_files(self, path, size):
        self.top_files.append((size, path))
        self.top_files.sort(key=lambda x: x[0], reverse=True)
        if len(self.top_files) > self.top_n_limit:
            self.top_files.pop()  # 移除最小的

    def get_summary(self):
        return {
            'file_types': sorted(self.file_types.items(), key=lambda x: x[1], reverse=True),
            'top_files': self.top_files
        }