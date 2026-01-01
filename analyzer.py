import os
import sys
import collections
import hashlib
import datetime
import subprocess
import re
import time
import pickle
import heapq
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


class DiskAnalyzer:
    """高性能磁盘分析器，支持实时进度和多模式扫描"""

    def __init__(self, root_path, max_depth=2, scan_method='auto',
                 num_workers=None, use_cache=True, ignore_errors=True):
        """
        初始化分析器

        Args:
            root_path: 要扫描的根路径
            max_depth: 最大扫描深度
            scan_method: 扫描方法 ['auto', 'find', 'walk', 'du', 'hybrid', 'fast']
            num_workers: 工作线程数
            use_cache: 是否使用缓存
            ignore_errors: 是否忽略权限错误
        """
        self.root_path = os.path.abspath(root_path)
        self.max_depth = max_depth
        self.num_workers = num_workers or (os.cpu_count() or 4)
        self.use_cache = use_cache
        self.ignore_errors = ignore_errors

        # 首先检测平台
        self._detect_platform()

        # 然后确定扫描方法
        self.scan_method = self._determine_method(scan_method)

        # 进度相关
        self.scan_stats = {
            'scanned_files': 0,
            'scanned_bytes': 0,
            'current_path': self.root_path
        }
        self.lock = threading.Lock()
        self.stop_event = None

        # 数据存储
        self.file_types = collections.defaultdict(int)
        self.top_files = []
        self.top_n_limit = 50
        self.flat_dirs = []
        self.duplicate_files = collections.defaultdict(list)
        self.cleanable_files = []
        self.history_data = []
        self.skipped_paths = []

        # 缓存
        self.cache_dir = Path.home() / '.cache' / 'disk_analyzer'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_key = hashlib.md5(self.root_path.encode()).hexdigest()
        self.cache_file = self.cache_dir / f"scan_{cache_key}.pkl"

        # 编译正则表达式
        self._compile_patterns()

        print(f"[初始化] 路径: {self.root_path}")
        print(f"[初始化] 方法: {self.scan_method}, 深度: {max_depth}, 线程: {self.num_workers}")

    def _detect_platform(self):
        """检测平台特性"""
        self.is_windows = os.name == 'nt'
        self.is_linux = os.name == 'posix'
        self.has_find = False
        self.has_du = False

        # 检查系统命令可用性（只在Linux下检查）
        if self.is_linux:
            try:
                subprocess.run(['find', '--version'], capture_output=True, check=True)
                self.has_find = True
            except:
                pass

            try:
                subprocess.run(['du', '--version'], capture_output=True, check=True)
                self.has_du = True
            except:
                pass

    def _determine_method(self, method):
        """智能确定扫描方法"""
        if method == 'auto':
            if self.is_windows:
                return 'fastwalk'  # Windows优化版本
            elif self.has_find:
                return 'fastfind'  # Linux快速find版本
            else:
                return 'walk'
        return method

    def _compile_patterns(self):
        """预编译正则表达式"""
        # 可清理文件模式
        self.cleanable_patterns = [
            (re.compile(r'\.cache$|[/\\]cache[/\\]|cached', re.I), '缓存文件'),
            (re.compile(r'\.log$|[/\\]logs[/\\]', re.I), '日志文件'),
            (re.compile(r'\.tmp$|[/\\]temp[/\\]|temp', re.I), '临时文件'),
            (re.compile(r'[/\\]downloads[/\\]|[/\\]download[/\\]', re.I), '下载文件'),
            (re.compile(r'\.bak$|backup', re.I), '备份文件'),
            (re.compile(r'thumb\.db$|\.DS_Store$', re.I), '系统缓存'),
        ]

        # 排除模式
        self.exclude_patterns = [
            re.compile(r'^/proc/'),
            re.compile(r'^/sys/'),
            re.compile(r'^/dev/'),
            re.compile(r'[/\\]\.git[/\\]'),
            re.compile(r'[/\\]__pycache__[/\\]'),
            re.compile(r'\.pyc$'),
        ]

        # Windows特定排除
        if self.is_windows:
            self.exclude_patterns.extend([
                re.compile(r'[/\\]System Volume Information[/\\]', re.I),
                re.compile(r'[/\\]\$Recycle\.Bin[/\\]', re.I),
                re.compile(r'[/\\]Windows[/\\]CSC[/\\]', re.I),
                re.compile(r'pagefile\.sys$', re.I),
                re.compile(r'hiberfil\.sys$', re.I),
                re.compile(r'swapfile\.sys$', re.I),
            ])

    def should_skip(self, path):
        """判断是否跳过路径"""
        for pattern in self.exclude_patterns:
            if pattern.search(path.replace('\\', '/')):
                return True
        return False

    def _update_progress(self, files=0, bytes=0, path=None):
        """更新扫描进度"""
        if self.lock:
            with self.lock:
                self.scan_stats['scanned_files'] += files
                self.scan_stats['scanned_bytes'] += bytes
                if path:
                    self.scan_stats['current_path'] = path

    def _cache_valid(self):
        """检查缓存有效性"""
        if not self.use_cache or not self.cache_file.exists():
            return False
        cache_age = time.time() - self.cache_file.stat().st_mtime
        return cache_age < 600  # 10分钟有效期

    def _load_cache(self):
        """加载缓存"""
        try:
            with open(self.cache_file, 'rb') as f:
                return pickle.load(f)
        except:
            return None

    def _save_cache(self, data):
        """保存缓存"""
        try:
            with open(self.cache_file, 'wb') as f:
                pickle.dump(data, f)
        except:
            pass

    def _get_disk_usage(self):
        """获取磁盘使用率（跨平台）"""
        try:
            # 尝试使用psutil
            try:
                import psutil
                return psutil.disk_usage(self.root_path).percent
            except ImportError:
                pass

            # Linux/Mac使用statvfs
            if hasattr(os, 'statvfs'):
                stat = os.statvfs(self.root_path)
                total = stat.f_blocks * stat.f_frsize
                free = stat.f_bavail * stat.f_frsize
                used = total - free
                return (used / total) * 100 if total > 0 else 0

            # Windows使用ctypes
            if self.is_windows:
                import ctypes
                drive = os.path.splitdrive(self.root_path)[0] + '\\'
                kernel32 = ctypes.windll.kernel32
                free_bytes = ctypes.c_ulonglong()
                total_bytes = ctypes.c_ulonglong()

                if kernel32.GetDiskFreeSpaceExW(drive, None, ctypes.byref(total_bytes), ctypes.byref(free_bytes)):
                    total = total_bytes.value
                    used = total - free_bytes.value
                    return (used / total) * 100 if total > 0 else 0

            return 75.0  # 默认值
        except:
            return 0.0

    def scan(self, on_progress=None, stop_event=None):
        """
        主扫描方法，支持进度回调和停止事件

        Args:
            on_progress: 进度回调函数
            stop_event: 停止事件

        Returns:
            扫描结果树
        """
        # 设置停止事件
        self.stop_event = stop_event or threading.Event()

        # 检查缓存
        if self.use_cache and self._cache_valid():
            cached = self._load_cache()
            if cached:
                print(f"[缓存] 使用缓存数据")
                return cached

        # 根据方法选择扫描策略
        print(f"[扫描] 使用 {self.scan_method} 方法")

        start_time = time.time()

        try:
            if self.scan_method == 'fastfind':
                dir_tree = self._scan_fast_find(on_progress)
            elif self.scan_method == 'fastwalk':
                dir_tree = self._scan_fast_walk(on_progress)
            elif self.scan_method == 'walk':
                dir_tree = self._scan_walk(on_progress)
            elif self.scan_method == 'du':
                dir_tree = self._scan_du()
            elif self.scan_method == 'hybrid':
                dir_tree = self._scan_hybrid(on_progress)
            else:
                dir_tree = self._scan_fast_walk(on_progress)  # 默认

            # 检查是否被停止
            if self.stop_event.is_set():
                print("[扫描] 扫描被停止")
                return self._create_partial_result()

            # 后处理
            self._post_process()

            # 构建完整结果
            result = self._build_result(dir_tree)

            # 保存缓存
            if self.use_cache:
                self._save_cache(result)

            elapsed = time.time() - start_time
            print(f"[完成] 扫描耗时: {elapsed:.2f}秒")
            print(f"[统计] 文件数: {self.scan_stats['scanned_files']}, 大小: {self.scan_stats['scanned_bytes']:,} 字节")

            return result

        except Exception as e:
            print(f"[错误] 扫描失败: {e}")
            import traceback
            traceback.print_exc()
            return self._create_error_result(str(e))

    def _scan_fast_find(self, on_progress=None):
        """使用find命令快速扫描（Linux优化版）"""
        if not self.has_find:
            return self._scan_walk(on_progress)

        files = []
        dir_sizes = collections.defaultdict(int)

        try:
            # 构建优化的find命令
            cmd = [
                'find', self.root_path,
                '-type', 'f',
                '!', '-path', '*/.*',  # 跳过隐藏文件
                '-printf', '%p\t%s\t%T@\n'
            ]

            print(f"[find] 执行命令: {' '.join(cmd[:5])}...")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=8192
            )

            file_count = 0
            batch_size = 1000
            batch_files = []

            for line in process.stdout:
                if self.stop_event.is_set():
                    process.terminate()
                    break

                if not line.strip():
                    continue

                try:
                    path, size_str, mtime_str = line.strip().split('\t')

                    # 跳过排除路径
                    if self.should_skip(path):
                        continue

                    size = int(size_str)
                    batch_files.append({
                        'path': path,
                        'size': size,
                        'mtime': float(mtime_str)
                    })

                    # 更新进度
                    file_count += 1
                    if file_count % batch_size == 0:
                        self._update_progress(batch_size, sum(f['size'] for f in batch_files), path)
                        if on_progress:
                            with self.lock:
                                on_progress(dict(self.scan_stats))

                        # 批量处理
                        self._process_batch_fast(batch_files, dir_sizes)
                        batch_files = []

                except ValueError:
                    continue

            # 处理剩余文件
            if batch_files:
                self._process_batch_fast(batch_files, dir_sizes)

            process.wait()

            return self._build_tree_from_dirs(dir_sizes)

        except Exception as e:
            print(f"[find] 命令失败: {e}")
            return self._scan_walk(on_progress)

    def _scan_fast_walk(self, on_progress=None):
        """快速walk扫描"""
        dir_sizes = collections.defaultdict(int)
        all_files = []

        # Windows上使用简单并行，避免ProcessPoolExecutor问题
        if self.is_windows:
            return self._scan_walk(on_progress)

        # Linux/Mac使用进程池
        try:
            from concurrent.futures import ProcessPoolExecutor
            import multiprocessing

            first_level_dirs = []
            with os.scandir(self.root_path) as it:
                for entry in it:
                    if entry.is_dir() and not entry.is_symlink():
                        if not self.should_skip(entry.path):
                            first_level_dirs.append(entry.path)

            print(f"[fastwalk] 发现 {len(first_level_dirs)} 个一级目录")

            # 限制并发数
            max_workers = min(self.num_workers, len(first_level_dirs), 8)

            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                for dir_path in first_level_dirs[:50]:  # 限制最多50个目录
                    future = executor.submit(self._scan_single_dir, dir_path, self.max_depth - 1)
                    futures[future] = dir_path

                completed = 0
                for future in as_completed(futures):
                    if self.stop_event.is_set():
                        executor.shutdown(wait=False, cancel_futures=True)
                        break

                    dir_path = futures[future]
                    try:
                        dir_files, dir_size = future.result(timeout=30)
                        all_files.extend(dir_files)
                        dir_sizes[dir_path] = dir_size

                        # 更新进度
                        self._update_progress(len(dir_files), dir_size, dir_path)
                        if on_progress:
                            with self.lock:
                                on_progress(dict(self.scan_stats))

                        completed += 1
                        if completed % 5 == 0:
                            print(f"[进度] 完成 {completed}/{len(futures)} 个目录")

                    except Exception as e:
                        print(f"[错误] 扫描目录 {dir_path} 失败: {e}")

        except Exception as e:
            print(f"[fastwalk] 并行扫描失败，回退到普通walk: {e}")
            return self._scan_walk(on_progress)

        # 扫描根目录文件
        try:
            with os.scandir(self.root_path) as it:
                for entry in it:
                    if self.stop_event.is_set():
                        break

                    if entry.is_file() and not entry.is_symlink():
                        if not self.should_skip(entry.path):
                            try:
                                size = entry.stat().st_size
                                all_files.append({
                                    'path': entry.path,
                                    'size': size,
                                    'ext': os.path.splitext(entry.name)[1].lower() or 'no_ext'
                                })
                                dir_sizes[self.root_path] += size
                                self._update_progress(1, size, entry.path)
                            except:
                                pass
        except:
            pass

        # 处理所有文件
        self._process_batch_fast(all_files, dir_sizes)

        return self._build_tree_from_dirs(dir_sizes)

    def _scan_single_dir(self, dir_path, max_depth):
        """扫描单个目录（用于并行）"""
        dir_files = []
        dir_size = 0

        try:
            for root, dirs, files in os.walk(dir_path):
                # 检查深度
                current_depth = root[len(dir_path):].count(os.sep)
                if current_depth > max_depth:
                    del dirs[:]
                    continue

                # 跳过排除目录
                dirs[:] = [d for d in dirs if not self.should_skip(os.path.join(root, d))]

                for file in files:
                    try:
                        full_path = os.path.join(root, file)
                        if self.should_skip(full_path):
                            continue

                        size = os.path.getsize(full_path)
                        dir_files.append({
                            'path': full_path,
                            'size': size,
                            'ext': os.path.splitext(file)[1].lower() or 'no_ext'
                        })
                        dir_size += size
                    except:
                        continue

        except Exception:
            pass

        return dir_files, dir_size

    def _scan_walk(self, on_progress=None):
        """传统walk扫描（兼容性好）"""
        dir_sizes = collections.defaultdict(int)
        all_files = []

        try:
            for root, dirs, files in os.walk(self.root_path, followlinks=False):
                if self.stop_event.is_set():
                    break

                # 更新当前路径
                self._update_progress(0, 0, root)
                if on_progress:
                    with self.lock:
                        on_progress(dict(self.scan_stats))

                # 控制深度
                current_depth = root[len(self.root_path):].count(os.sep)
                if current_depth > self.max_depth:
                    del dirs[:]
                    continue

                # 跳过排除目录
                dirs[:] = [d for d in dirs if not self.should_skip(os.path.join(root, d))]

                # 处理文件
                for file in files:
                    try:
                        full_path = os.path.join(root, file)
                        if self.should_skip(full_path):
                            continue

                        size = os.path.getsize(full_path)
                        all_files.append({
                            'path': full_path,
                            'size': size,
                            'ext': os.path.splitext(file)[1].lower() or 'no_ext'
                        })
                        dir_sizes[root] += size
                        dir_sizes[self.root_path] += size

                        # 更新进度
                        self._update_progress(1, size, full_path)

                    except (PermissionError, OSError):
                        continue

        except Exception as e:
            print(f"[walk] 扫描出错: {e}")

        # 批量处理文件
        self._process_batch_fast(all_files, dir_sizes)

        return self._build_tree_from_dirs(dir_sizes)

    def _scan_du(self):
        """使用du命令快速获取大小"""
        try:
            if self.is_windows:
                # Windows使用dir命令
                cmd = f'cmd /c "dir /s /a-d "{self.root_path}" 2>nul"'
            else:
                cmd = f'du -sb "{self.root_path}" 2>/dev/null'

            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            if self.is_windows:
                # 解析Windows dir输出
                lines = result.stdout.split('\n')
                for line in reversed(lines):
                    if '个文件' in line or 'File(s)' in line:
                        parts = line.split()
                        for part in parts:
                            part = part.replace(',', '')
                            if part.isdigit():
                                total_size = int(part)
                                break
                        else:
                            total_size = 0
                        break
                else:
                    total_size = 0
            else:
                # 解析Linux du输出
                if result.returncode == 0:
                    total_size = int(result.stdout.split()[0])
                else:
                    total_size = 0

            return {
                'path': self.root_path,
                'name': os.path.basename(self.root_path),
                'size': total_size,
                'children': [],
                'percentage': 100
            }

        except:
            return {
                'path': self.root_path,
                'name': os.path.basename(self.root_path),
                'size': 0,
                'children': [],
                'percentage': 100
            }

    def _scan_hybrid(self, on_progress=None):
        """混合扫描：先用du快速，再用walk补充"""
        # 先用du获取总大小
        base_tree = self._scan_du()
        total_size = base_tree['size']

        if total_size > 10 * 1024 ** 3:  # 大于10GB，只扫描两层
            scan_depth = min(self.max_depth, 2)
        else:
            scan_depth = self.max_depth

        # 使用walk扫描细节
        backup_analyzer = DiskAnalyzer(
            self.root_path,
            max_depth=scan_depth,
            scan_method='walk',
            num_workers=self.num_workers,
            use_cache=False,
            ignore_errors=self.ignore_errors
        )

        detailed_tree = backup_analyzer._scan_walk(on_progress)

        # 合并结果
        base_tree['size'] = max(base_tree['size'], detailed_tree.get('size', 0))
        if 'children' in detailed_tree:
            base_tree['children'] = detailed_tree['children']

        # 合并统计数据
        self.scan_stats['scanned_files'] += backup_analyzer.scan_stats['scanned_files']
        self.scan_stats['scanned_bytes'] += backup_analyzer.scan_stats['scanned_bytes']

        return base_tree

    def _process_batch_fast(self, files, dir_sizes):
        """快速处理一批文件"""
        for file_info in files:
            # 文件类型统计
            ext = file_info.get('ext', 'no_ext')
            if not ext:
                ext = os.path.splitext(file_info['path'])[1].lower() or 'no_ext'
            self.file_types[ext] += file_info['size']

            # Top文件维护
            size = file_info['size']
            path = file_info['path']

            if len(self.top_files) < self.top_n_limit:
                heapq.heappush(self.top_files, (size, path))
            elif size > self.top_files[0][0]:
                heapq.heapreplace(self.top_files, (size, path))

            # 识别可清理文件
            self._identify_cleanable_file_fast(file_info)

            # 更新目录大小
            dir_path = os.path.dirname(path)
            dir_sizes[dir_path] = dir_sizes.get(dir_path, 0) + size

            # 更新根目录大小
            dir_sizes[self.root_path] = dir_sizes.get(self.root_path, 0) + size

    def _identify_cleanable_file_fast(self, file_info):
        """快速识别可清理文件"""
        path_lower = file_info['path'].lower()

        for pattern, file_type in self.cleanable_patterns:
            if pattern.search(path_lower):
                self.cleanable_files.append({
                    'path': file_info['path'],
                    'size': file_info['size'],
                    'type': file_type
                })
                break

    def _build_tree_from_dirs(self, dir_sizes):
        """从目录大小构建树"""
        if not dir_sizes:
            return {
                'path': self.root_path,
                'name': os.path.basename(self.root_path),
                'size': 0,
                'children': [],
                'percentage': 100
            }

        # 构建树结构
        root_size = dir_sizes.get(self.root_path, 0)
        root_tree = {
            'path': self.root_path,
            'name': os.path.basename(self.root_path),
            'size': root_size,
            'children': [],
            'percentage': 100
        }

        # 添加直接子目录
        child_dirs = {}
        for dir_path, size in dir_sizes.items():
            if dir_path == self.root_path:
                continue

            parent = os.path.dirname(dir_path)
            if parent == self.root_path:
                child_dirs[dir_path] = size

        # 按大小排序并添加
        for dir_path, size in sorted(child_dirs.items(), key=lambda x: x[1], reverse=True)[:100]:
            root_tree['children'].append({
                'path': dir_path,
                'name': os.path.basename(dir_path),
                'size': size,
                'children': [],
                'percentage': (size / root_size * 100) if root_size > 0 else 0
            })

        return root_tree

    def _post_process(self):
        """后处理数据"""
        # 转换top_files为排序列表
        self.top_files = sorted(self.top_files, reverse=True)

        # 限制cleanable_files数量
        if len(self.cleanable_files) > 200:
            self.cleanable_files = self.cleanable_files[:200]

        # 生成模拟历史数据
        self._generate_mock_history()

    def _generate_mock_history(self):
        """生成模拟历史数据"""
        now = datetime.datetime.now()
        self.history_data = []

        base_size = self.scan_stats['scanned_bytes']

        for i in range(30):
            date = now - datetime.timedelta(days=29 - i)
            # 基于实际大小生成变化趋势
            variation = 1.0 + (i % 10 - 5) * 0.02  # ±10%变化
            self.history_data.append({
                'date': date.strftime('%Y-%m-%d'),
                'usage': min(95, 40 + (i % 10) * 3 + (i // 10) * 2),
                'size': int(base_size * variation)
            })

    def _build_result(self, dir_tree):
        """构建最终结果"""
        total_size = dir_tree.get('size', 0)

        # 扁平目录统计
        flat_dirs = []
        for dir_info in dir_tree.get('children', []):
            percentage = (dir_info['size'] / total_size * 100) if total_size > 0 else 0
            flat_dirs.append({
                'path': dir_info['path'],
                'size': dir_info['size'],
                'percentage': percentage
            })

        # 安全建议
        security_suggestions = []
        for file in self.cleanable_files[:50]:
            path_lower = file['path'].lower()

            if 'cache' in path_lower or 'temp' in path_lower:
                level = 3  # 低风险
            elif 'log' in path_lower:
                level = 2  # 中风险
            elif 'system' in path_lower or 'etc' in path_lower or 'windows' in path_lower:
                level = 1  # 高风险
            else:
                level = 4  # 安全

            security_suggestions.append({
                'path': file['path'],
                'size': file['size'],
                'security_level': level,
                'whitelist': False,
                'suggestion': self._get_security_suggestion(level)
            })

        # 获取磁盘使用率
        disk_usage = self._get_disk_usage()

        result = {
            'path': self.root_path,
            'total_size': total_size,
            'dir_tree': dir_tree,
            'flat_dirs': sorted(flat_dirs, key=lambda x: x['size'], reverse=True)[:100],
            'file_types': dict(self.file_types),
            'duplicate_files': dict(self.duplicate_files),
            'cleanable_files': self.cleanable_files[:100],
            'security_suggestions': security_suggestions,
            'history_data': self.history_data,
            'disk_usage': disk_usage,
            'top_files': [{'path': p, 'size': s} for s, p in self.top_files[:50]],
            'scan_stats': dict(self.scan_stats),
            'scan_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        return result

    def _create_partial_result(self):
        """创建部分扫描结果"""
        return {
            'path': self.root_path,
            'total_size': self.scan_stats['scanned_bytes'],
            'dir_tree': {
                'path': self.root_path,
                'name': os.path.basename(self.root_path),
                'size': self.scan_stats['scanned_bytes'],
                'children': [],
                'percentage': 100
            },
            'flat_dirs': [],
            'file_types': dict(self.file_types),
            'duplicate_files': {},
            'cleanable_files': self.cleanable_files,
            'security_suggestions': [],
            'history_data': [],
            'disk_usage': self._get_disk_usage(),
            'top_files': [{'path': p, 'size': s} for s, p in self.top_files],
            'partial': True,
            'scan_stats': dict(self.scan_stats)
        }

    def _create_error_result(self, error_msg):
        """创建错误结果"""
        return {
            'path': self.root_path,
            'total_size': 0,
            'dir_tree': {
                'path': self.root_path,
                'name': os.path.basename(self.root_path),
                'size': 0,
                'children': [],
                'percentage': 100
            },
            'error': error_msg,
            'scan_stats': dict(self.scan_stats)
        }

    def _get_security_suggestion(self, level):
        """获取安全建议"""
        suggestions = {
            1: '高风险文件，禁止删除！可能导致系统/程序异常',
            2: '中风险文件，建议备份后再删除，删除前确认不再需要',
            3: '低风险文件，可安全删除，不会影响系统运行',
            4: '安全文件，可放心删除，推荐立即清理'
        }
        return suggestions.get(level, '请谨慎评估后操作')

    def get_enhanced_summary(self, total_size=None):
        """
        获取增强摘要（兼容接口）

        注意：你的analyzer的scan()已经返回完整数据，
        这个方法主要是为了兼容原版analyzer的接口
        """
        # 如果已经有扫描结果，直接返回
        if hasattr(self, '_last_scan_result'):
            return self._last_scan_result

        # 否则执行扫描
        result = self.scan()
        self._last_scan_result = result
        return result

    def get_tui_data(self):
        """获取TUI界面数据"""
        result = self.scan() if not hasattr(self, '_last_scan_result') else self._last_scan_result

        tui_data = {
            'path': result.get('path', self.root_path),
            'size': result.get('total_size', 0),
            'children': []
        }

        # 添加目录
        dir_tree = result.get('dir_tree', {})
        for child in dir_tree.get('children', []):
            tui_data['children'].append({
                'path': child.get('path', ''),
                'name': child.get('name', ''),
                'size': child.get('size', 0),
                'children': child.get('children', [])
            })

        # 添加文件
        for file_info in result.get('top_files', [])[:30]:
            tui_data['children'].append({
                'path': file_info.get('path', ''),
                'name': os.path.basename(file_info.get('path', '')),
                'size': file_info.get('size', 0),
                'children': None
            })

        return tui_data



FastDiskAnalyzer = DiskAnalyzer
