import os
import collections
import hashlib
import datetime


class DiskAnalyzer:
    def __init__(self, root_path, max_depth=2):
        self.root_path = os.path.abspath(root_path)
        self.max_depth = max_depth

        self.file_types = collections.defaultdict(int)
        self.top_files = []  # (size, path)
        self.top_n_limit = 20

        self.flat_dirs = []
        self.duplicate_files = collections.defaultdict(list)
        self.cleanable_files = []
        self.history_data = []
        self.disk_usage = self._get_disk_usage()

        # 扫描过程统计（用于命令行实时展示）
        self.scanned_files_count = 0
        self.scanned_bytes = 0
        self.current_path = ""
        self.scan_started_at = None

    def scan(self, on_progress=None, stop_event=None):
        self.scanned_files_count = 0
        self.scanned_bytes = 0
        self.current_path = self.root_path
        self.scan_started_at = datetime.datetime.now()

        # 每次扫描前清空，避免累计旧数据
        self.cleanable_files = []
        self.file_types = collections.defaultdict(int)
        self.top_files = []
        self.flat_dirs = []
        self.duplicate_files = collections.defaultdict(list)
        self.history_data = []
        self.disk_usage = self._get_disk_usage()

        dir_tree = self._scan_recursive(
            self.root_path, 0, on_progress=on_progress, stop_event=stop_event
        )

        self._process_duplicates()

        # A：不再二次扫描，只排序/截断
        self._identify_cleanable_files()

        self._generate_mock_history()
        return dir_tree

    def _emit_progress(self, on_progress):
        if not on_progress:
            return
        try:
            on_progress({
                "scanned_files": self.scanned_files_count,
                "scanned_bytes": self.scanned_bytes,
                "current_path": self.current_path,
                "root_path": self.root_path,
                "started_at": self.scan_started_at,
            })
        except Exception:
            pass

    # -------- Cleanable: 扫描过程中收集（不再二次扫描） --------
    def _cleanable_level_for_name(self, name: str):
        patterns = [
            ('.cache', 4),
            ('cache', 4),
            ('tmp', 4),
            ('temp', 4),
            ('node_modules', 3),
            ('__pycache__', 3),
            ('.log', 2),
            ('.bak', 2),
            ('.old', 2),
            ('.swp', 2),
        ]
        low = (name or "").lower()
        for pat, level in patterns:
            if pat.startswith('.') and low.endswith(pat):
                return level
            if pat in low:
                return level
        return None

    def _maybe_add_cleanable(self, path: str, name: str, size: int):
        level = self._cleanable_level_for_name(name)
        if level is None:
            return
        self.cleanable_files.append({
            'path': path,
            'name': name,
            'size': size,
            'risk_level': level,
            'suggestion': self._get_security_suggestion(level)
        })
    # ------------------------------------------------------

    def _scan_recursive(self, current_path, current_depth, on_progress=None, stop_event=None):
        dir_stat = {
            'path': current_path,
            'name': os.path.basename(current_path) or current_path,
            'size': 0,
            'children': [],
            'percentage': 0
        }

        self.current_path = current_path
        self._emit_progress(on_progress)

        try:
            with os.scandir(current_path) as it:
                for entry in it:
                    if stop_event is not None and getattr(stop_event, "is_set", None) and stop_event.is_set():
                        return dir_stat

                    if entry.is_symlink():
                        continue

                    if entry.is_file():
                        try:
                            st = entry.stat()
                            size = st.st_size
                            dir_stat['size'] += size

                            # 扫描进度统计
                            self.scanned_files_count += 1
                            self.scanned_bytes += size
                            self.current_path = entry.path
                            self._emit_progress(on_progress)

                            # 文件类型统计
                            ext = os.path.splitext(entry.name)[1].lower() or "No Ext"
                            self.file_types[ext] += size

                            # Top-N
                            self._update_top_files(entry.path, size)

                            # cleanable：扫描时收集
                            self._maybe_add_cleanable(entry.path, entry.name, size)

                            # 重复检测（注意：MD5 仍会慢，这是你后续如果还慢再做 B）
                            file_hash = self._get_file_hash(entry.path)
                            if file_hash:
                                self.duplicate_files[file_hash].append({
                                    'path': entry.path,
                                    'size': size,
                                    'mtime': st.st_mtime
                                })

                            dir_stat['children'].append({
                                'path': entry.path,
                                'name': entry.name,
                                'size': size,
                                'children': None
                            })
                        except (PermissionError, OSError):
                            pass

                    elif entry.is_dir():
                        if current_depth < self.max_depth:
                            child_stat = self._scan_recursive(
                                entry.path, current_depth + 1,
                                on_progress=on_progress, stop_event=stop_event
                            )
                            dir_stat['size'] += child_stat['size']
                            dir_stat['children'].append(child_stat)

                            self._maybe_add_cleanable(entry.path, entry.name, child_stat.get('size', 0))
                        else:
                            size = self._get_deep_size(entry.path)
                            dir_stat['size'] += size
                            dir_stat['children'].append({
                                'path': entry.path,
                                'name': entry.name,
                                'size': size,
                                'children': []
                            })
                            self._maybe_add_cleanable(entry.path, entry.name, size)

            dir_stat['children'].sort(key=lambda x: x['size'], reverse=True)
            self.flat_dirs.append({'path': current_path, 'size': dir_stat['size'], 'percentage': 0})
            return dir_stat

        except PermissionError:
            return dir_stat

    def _get_deep_size(self, path):
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
            self.top_files.pop()

    def _get_file_hash(self, filepath, block_size=65536):
        try:
            hasher = hashlib.md5()
            with open(filepath, 'rb') as f:
                buf = f.read(block_size)
                while buf:
                    hasher.update(buf)
                    buf = f.read(block_size)
            return hasher.hexdigest()
        except:
            return None

    def _process_duplicates(self):
        dup = {}
        for h, files in self.duplicate_files.items():
            if len(files) > 1:
                files.sort(key=lambda x: x['mtime'], reverse=True)
                dup[h] = files
        self.duplicate_files = dup

    def _identify_cleanable_files(self):
        # A：不再二次扫描，只排序
        self.cleanable_files.sort(key=lambda x: x.get('size', 0), reverse=True)
        if len(self.cleanable_files) > 2000:
            self.cleanable_files = self.cleanable_files[:2000]

    def _generate_mock_history(self):
        """生成模拟的历史磁盘使用数据（兼容 reporter.py：date + size + usage）"""
        self.history_data = []
        now = datetime.datetime.now()

        used_now = int(self.disk_usage.get("used", 0))
        total = int(self.disk_usage.get("total", 0))

        # 兜底，避免除零/缺字段
        if total <= 0:
            total = max(used_now, 1)
        if used_now < 0:
            used_now = 0
        if used_now > total:
            used_now = total

        # 生成 30 天：size(bytes) + usage(百分比)
        swing = max(1, int(total * 0.005))  # 总量的 0.5% 波动
        for i in range(30):
            day = now - datetime.timedelta(days=29 - i)

            # 做一点平滑趋势：前半段略低，后半段略高
            drift = int((i - 15) * (swing / 15))  # 约 [-swing, +swing]
            size = used_now + drift
            if size < 0:
                size = 0
            if size > total:
                size = total

            usage = (size / total) * 100.0 if total > 0 else 0.0

            self.history_data.append({
                "date": day.strftime("%Y-%m-%d"),
                "size": int(size),            # bytes
                "usage": round(usage, 2),     # 百分比（reporter.py 需要）
        })


    def _get_disk_usage(self):
        try:
            st = os.statvfs(self.root_path)
            total = st.f_frsize * st.f_blocks
            free = st.f_frsize * st.f_bfree
            used = total - free
            used_percent = (used / total) * 100 if total > 0 else 0
            return {"total": total, "used": used, "free": free, "used_percent": round(used_percent, 2)}
        except:
            return {"total": 0, "used": 0, "free": 0, "used_percent": 0}

    def get_enhanced_summary(self, dir_tree):
        total_size = (dir_tree or {}).get('size', 0)

        # reporter.py 需要 duplicate_files 是 “list of groups(list)”
        # 同时我们按“浪费空间”排序（除去最新那个，其余算浪费）
        dup_groups = []
        for _h, files in self.duplicate_files.items():
            if not files or len(files) < 2:
                continue
            # files 已在 _process_duplicates 里按 mtime desc 排过序（最新在前）
            wasted = sum(f.get("size", 0) for f in files[1:])
            dup_groups.append((wasted, files))

        dup_groups.sort(key=lambda x: x[0], reverse=True)
        duplicate_files_for_reporter = [files for wasted, files in dup_groups]

        enhanced_summary = {
            "root_path": self.root_path,
            "total_size": total_size,
            "disk_usage": self.disk_usage,

            # reporter.py 的 pie 用 dict.values()
            "file_types": dict(self.file_types),

            "top_files": [
                {"path": p, "size": s, "percentage": (s / total_size) * 100 if total_size > 0 else 0}
                for s, p in self.top_files
            ],

            "flat_dirs": [],
            # ✅ 关键：这里改成 reporter 期望的结构
            "duplicate_files": duplicate_files_for_reporter,

            "cleanable_files": self.cleanable_files[:50],
            "history_data": self.history_data,

            # reporter.py 需要 dir_tree
            "dir_tree": self._add_percentages(dir_tree, total_size) if dir_tree else {},
        }

        for d in self.flat_dirs:
            d["percentage"] = (d["size"] / total_size) * 100 if total_size > 0 else 0
            enhanced_summary["flat_dirs"].append(d)
        enhanced_summary["flat_dirs"].sort(key=lambda x: x["size"], reverse=True)

        return enhanced_summary

    def _add_percentages(self, dir_tree, total_size):
        if not dir_tree:
            return dir_tree
        if dir_tree.get('children') is None:
            return dir_tree

        # 根节点 percentage 也补上
        dir_tree['percentage'] = (dir_tree.get('size', 0) / total_size) * 100 if total_size > 0 else 0

        for child in dir_tree.get('children', []):
            if child.get('children') is not None:
                child['percentage'] = (child.get('size', 0) / total_size) * 100 if total_size > 0 else 0
                self._add_percentages(child, total_size)
        return dir_tree

    def _get_security_suggestion(self, level):
        suggestions = {
            1: '高风险文件，禁止删除！可能导致系统/程序异常',
            2: '中风险文件，建议备份后再删除，删除前确认不再需要',
            3: '低风险文件，可安全删除，不会影响系统运行',
            4: '安全文件，可放心删除，推荐立即清理'
        }
        return suggestions.get(level, '请谨慎评估后操作')

