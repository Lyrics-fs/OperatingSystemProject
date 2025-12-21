import os
import collections
import hashlib
import datetime


class DiskAnalyzer:
    def __init__(self, root_path, max_depth=2):
        self.root_path = os.path.abspath(root_path)
        self.max_depth = max_depth
        self.file_types = collections.defaultdict(int) 
        self.top_files = []  # 存储 (size, path)
        self.top_n_limit = 20
        self.flat_dirs = []  # 扁平目录统计
        self.duplicate_files = collections.defaultdict(list)  # 重复文件 (hash: [files])
        self.cleanable_files = []  # 可清理文件
        self.history_data = []  # 历史数据（模拟）
        self.disk_usage = self._get_disk_usage()  # 磁盘使用率

    def scan(self):
        """执行扫描并返回目录树结构"""
        dir_tree = self._scan_recursive(self.root_path, 0)
        self._process_duplicates()
        self._identify_cleanable_files()
        self._generate_mock_history()
        return dir_tree

    def _scan_recursive(self, current_path, current_depth):
        dir_stat = {
            'path': current_path,
            'name': os.path.basename(current_path) or current_path,
            'size': 0,
            'children': [],
            'percentage': 0  # 后续计算
        }

        try:
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

                            # 计算文件哈希用于检测重复
                            file_hash = self._get_file_hash(entry.path)
                            if file_hash:
                                self.duplicate_files[file_hash].append({
                                    'path': entry.path,
                                    'size': size,
                                    'mtime': entry.stat().st_mtime
                                })

                            dir_stat['children'].append({
                                'path': entry.path,
                                'name': entry.name,
                                'size': size,
                                'children': None  # 用 None 区分文件
                            })
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
                            dir_stat['children'].append({
                                'path': entry.path,
                                'name': entry.name,
                                'size': size,
                                'children': []
                            })

            # 按大小对子目录排序
            dir_stat['children'].sort(key=lambda x: x['size'], reverse=True)
            self.flat_dirs.append({
                'path': current_path,
                'size': dir_stat['size'],
                'percentage': 0  # 后续计算
            })
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

    def _get_file_hash(self, path, block_size=65536):
        """计算文件哈希用于检测重复文件"""
        try:
            if os.path.getsize(path) < 1024 * 1024:  # 小于1MB的文件不检测重复
                return None
                
            hasher = hashlib.md5()
            with open(path, 'rb') as f:
                buf = f.read(block_size)
                while buf:
                    hasher.update(buf)
                    buf = f.read(block_size)
            return hasher.hexdigest()
        except:
            return None

    def _process_duplicates(self):
        """处理重复文件，只保留有多个实例的组"""
        # 创建新的defaultdict来存储处理后的结果
        result = collections.defaultdict(list)
        for hash_key, files in self.duplicate_files.items():
            if len(files) > 1:
                # 按修改时间排序
                files.sort(key=lambda x: x['mtime'], reverse=True)
                result[hash_key] = files
        self.duplicate_files = result

    def _identify_cleanable_files(self):
        """识别可清理文件"""
        cleanable_patterns = {
            '缓存文件': ['.cache', '/cache/', 'cached'],
            '日志文件': ['.log', '/logs/'],
            '临时文件': ['.tmp', '/tmp/', 'temp'],
            '下载文件': ['/downloads/', '/download/']
        }

        for size, path in self.top_files:
            for file_type, patterns in cleanable_patterns.items():
                if any(pattern in path.lower() for pattern in patterns):
                    self.cleanable_files.append({
                        'path': path,
                        'size': size,
                        'type': file_type
                    })
                    break

    def _get_disk_usage(self):
        """获取磁盘使用率"""
        try:
            stat = os.statvfs(self.root_path)
            return (1 - stat.f_bavail / stat.f_blocks) * 100
        except:
            return 0

    def _generate_mock_history(self):
        """生成模拟的历史数据"""
        now = datetime.datetime.now() 
        for i in range(30):
            date = now - datetime.timedelta(days=29 - i)
            self.history_data.append({
                'date': date.strftime('%Y-%m-%d'),
                'usage': min(90, 40 + (i % 10) * 3 + (i // 10) * 2),
                'size': (200 + i * 2.5) * 1024 * 1024 * 1024  # 转换为字节
            })

    def get_enhanced_summary(self, total_size):
        """生成增强版摘要数据"""
        # 计算百分比
        for dir_info in self.flat_dirs:
            dir_info['percentage'] = (dir_info['size'] / total_size) * 100 if total_size > 0 else 0
        
        # 排序扁平目录
        self.flat_dirs.sort(key=lambda x: x['size'], reverse=True)
        
        # 生成安全建议
        security_suggestions = []
        for file in self.cleanable_files[:10]:
            if 'cache' in file['type'].lower() or 'temp' in file['type'].lower():
                level = 3  # 低风险
            elif 'log' in file['type'].lower():
                level = 2  # 中风险
            elif 'system' in file['path'].lower():
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

        return {
            'path': self.root_path,
            'total_size': total_size,
            'dir_tree': self._add_percentages(self.scan()),
            'flat_dirs': self.flat_dirs,
            'file_types': dict(self.file_types),
            'duplicate_files': self.duplicate_files,
            'cleanable_files': self.cleanable_files,
            'security_suggestions': security_suggestions,
            'history_data': self.history_data,
            'disk_usage': self.disk_usage
        }

    def _add_percentages(self, dir_tree, total_size=None):
        """为目录树添加百分比"""
        if total_size is None:
            total_size = dir_tree['size']
            
        for child in dir_tree.get('children', []):
            if child['children'] is not None:  # 是目录
                child['percentage'] = (child['size'] / total_size) * 100 if total_size > 0 else 0
                self._add_percentages(child, total_size)
        return dir_tree

    def _get_security_suggestion(self, level):
        """获取安全删除建议"""
        suggestions = {
            1: '高风险文件，禁止删除！可能导致系统/程序异常',
            2: '中风险文件，建议备份后再删除，删除前确认不再需要',
            3: '低风险文件，可安全删除，不会影响系统运行',
            4: '安全文件，可放心删除，推荐立即清理'
        }
        return suggestions.get(level, '请谨慎评估后操作')

