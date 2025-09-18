import subprocess
import json
from typing import List, Tuple

# ExifTool CLI 支持 (通过系统PATH中的exiftool.exe)
_HAS_EXIFTOOL = False
try:
    # 测试 exiftool 是否在系统 PATH 中可用
    result = subprocess.run(['exiftool', '-ver'], capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        _HAS_EXIFTOOL = True
except Exception:
    pass


def _from_exiftool_cli(path: str) -> Tuple[List[str], List[str]]:
    """使用系统PATH中的exiftool.exe CLI获取所有metadata"""
    people: List[str] = []
    tags: List[str] = []
    
    if not _HAS_EXIFTOOL:
        return people, tags
    
    try:
        # 第一次尝试：使用标准UTF-8设置
        result = None
        try:
            result = subprocess.run([
                'exiftool', 
                '-json',  # JSON 输出格式
                '-all',   # 获取所有 metadata
                '-charset', 'utf8',  # 确保正确的字符编码
                '-coordFormat', '%.6f',  # 坐标格式
                '-dateFormat', '%Y:%m:%d %H:%M:%S',  # 日期格式
                '-escape', 'xml',  # XML转义特殊字符
                '-ignoreMinorErrors',  # 忽略小错误
                path
            ], capture_output=True, text=True, timeout=30, encoding='utf-8')
        except Exception:
            pass
        
        # 如果第一次尝试失败或返回空结果，尝试不同的编码设置
        if not result or result.returncode != 0 or not result.stdout.strip():
            try:
                result = subprocess.run([
                    'exiftool', 
                    '-json',
                    '-all',
                    '-charset', 'filename=utf8',  # 文件名使用UTF-8
                    '-charset', 'exif=utf8',      # EXIF使用UTF-8
                    '-charset', 'iptc=utf8',      # IPTC使用UTF-8
                    '-charset', 'xmp=utf8',       # XMP使用UTF-8
                    '-ignoreMinorErrors',
                    path
                ], capture_output=True, text=True, timeout=30, encoding='utf-8')
            except Exception:
                pass
        
        # 如果仍然失败，尝试最基本的设置
        if not result or result.returncode != 0:
            try:
                # 对于Windows，有时需要使用系统默认编码
                import locale
                system_encoding = locale.getpreferredencoding()
                
                raw_result = subprocess.run([
                    'exiftool', 
                    '-json',
                    '-all',
                    '-charset', system_encoding,  # 使用系统编码
                    path
                ], capture_output=True, timeout=30)
                
                # 手动处理字节到字符串的转换
                if raw_result.stdout and raw_result.returncode == 0:
                    stdout_text = ""
                    try:
                        # 尝试用UTF-8解码
                        stdout_text = raw_result.stdout.decode('utf-8')
                    except UnicodeDecodeError:
                        try:
                            # 尝试用系统编码解码
                            stdout_text = raw_result.stdout.decode(system_encoding, errors='replace')
                        except:
                            # 最后尝试用错误替换方式解码
                            stdout_text = raw_result.stdout.decode('utf-8', errors='replace')
                    
                    # 创建一个模拟的result对象
                    class MockResult:
                        def __init__(self, stdout, returncode):
                            self.stdout = stdout
                            self.returncode = returncode
                    
                    result = MockResult(stdout_text, raw_result.returncode)
                            
            except Exception:
                return people, tags
        
        if result and result.returncode != 0:
            return people, tags
        
        if not result:
            return people, tags
        
        # 解析 JSON 输出
        try:
            metadata_list = json.loads(result.stdout)
            if not metadata_list or not isinstance(metadata_list, list):
                return people, tags
            
            metadata = metadata_list[0]  # exiftool 返回的是数组，取第一个元素
            
            # 提取标签 (Tags/Keywords)
            tag_fields = [
                'Keywords', 'XPKeywords', 'Subject', 'HierarchicalKeywords',
                'TagsList', 'CatalogSets', 'SupplementalCategories',
                'XPSubject', 'XMP-dc:Subject', 'XMP-lr:HierarchicalSubject',
                'XMP-photoshop:Keywords', 'IPTC:Keywords', 'EXIF:XPKeywords'
            ]
            
            for field in tag_fields:
                value = metadata.get(field)
                if value:
                    if isinstance(value, str):
                        # 分割字符串标签 (可能用分号、逗号或其他分隔符)
                        if ';' in value:
                            tags.extend([tag.strip() for tag in value.split(';') if tag.strip()])
                        elif ',' in value:
                            tags.extend([tag.strip() for tag in value.split(',') if tag.strip()])
                        else:
                            tags.append(value.strip())
                    elif isinstance(value, list):
                        # 如果是列表，直接扩展
                        tags.extend([str(tag).strip() for tag in value if str(tag).strip()])
            
            # 提取人员信息 (People/Faces)
            people_fields = [
                'RegionName', 'PersonInImage', 'PersonDisplayName', 
                'XMP-mwg-rs:Name', 'XMP-MP:PersonDisplayName',
                'XMP-Iptc4xmpExt:PersonInImage', 'RegionInfo',
                'FaceName', 'PeopleKeywords'
            ]
            
            for field in people_fields:
                value = metadata.get(field)
                if value:
                    if isinstance(value, str):
                        if ';' in value:
                            people.extend([person.strip() for person in value.split(';') if person.strip()])
                        elif ',' in value:
                            people.extend([person.strip() for person in value.split(',') if person.strip()])
                        else:
                            people.append(value.strip())
                    elif isinstance(value, list):
                        people.extend([str(person).strip() for person in value if str(person).strip()])
            
            # 特殊处理：从 RegionInfo 中提取人员信息
            region_info = metadata.get('RegionInfo')
            if region_info and isinstance(region_info, str):
                # 尝试解析可能的 JSON 字符串
                try:
                    import re
                    # 寻找人名模式
                    name_pattern = r'"Name"\s*:\s*"([^"]+)"'
                    matches = re.findall(name_pattern, region_info)
                    people.extend([name.strip() for name in matches if name.strip()])
                except Exception:
                    pass
            
            # 字符串清理函数，处理编码问题
            def _clean_string(s: str) -> str:
                """清理字符串，处理编码问题"""
                if not s:
                    return s
                
                # 尝试修复常见的编码问题
                try:
                    # 特殊处理：检查是否是Windows下ExifTool的编码问题
                    # 这种情况下，中文字符可能被错误编码
                    
                    # 方法1: 检查是否包含明显的乱码字符
                    # 常见的乱码模式：包含特定Unicode范围的字符
                    suspicious_chars = any(
                        0x4E00 <= ord(c) <= 0x9FFF and  # CJK统一汉字
                        c in '闄堝啺濂囧鍋夸奇妙妈妹' for c in s  # 常见乱码字符
                    )
                    
                    if suspicious_chars:
                        # 这可能是编码问题，尝试跳过此字符串
                        return ""
                    
                    # 方法2: 尝试重新编码修复
                    # 对于Windows EXIF数据，有时需要特殊处理
                    try:
                        # 尝试处理可能的CP936(GBK)编码问题
                        if any(ord(c) > 127 for c in s):
                            # 包含非ASCII字符，可能需要修复
                            # 尝试将字符串当作错误解析的结果进行修复
                            
                            # 检查是否可能是UTF-8字节被当作其他编码解析
                            for source_encoding in ['cp1252', 'iso-8859-1']:
                                for target_encoding in ['utf-8', 'gbk', 'gb2312']:
                                    try:
                                        # 尝试反向工程修复
                                        temp_bytes = s.encode(source_encoding, errors='ignore')
                                        if temp_bytes:
                                            fixed = temp_bytes.decode(target_encoding, errors='ignore')
                                            if fixed and fixed != s and len(fixed) > 0:
                                                # 验证修复是否合理（包含合理的中文字符）
                                                if any(0x4E00 <= ord(c) <= 0x9FFF for c in fixed):
                                                    return fixed
                                    except:
                                        continue
                    except:
                        pass
                    
                    # 方法3: 如果包含明显不合理的字符，过滤掉
                    filtered_chars = []
                    for c in s:
                        code = ord(c)
                        # 保留正常的字符范围
                        if (32 <= code <= 126) or \
                           (0x4E00 <= code <= 0x9FFF) or \
                           (0x3400 <= code <= 0x4DBF) or \
                           (0x20000 <= code <= 0x2A6DF) or \
                           code in [0x3000, 0xFF01, 0xFF1A, 0xFF1B, 0xFF1F]:  # 常见中文标点
                            filtered_chars.append(c)
                    
                    filtered_s = ''.join(filtered_chars)
                    if filtered_s != s and len(filtered_s) > 0:
                        return filtered_s
                        
                except Exception:
                    pass
                
                # 如果所有修复尝试都失败，返回原始字符串
                return s
            
            # 清理人员和标签列表
            def _clean_and_unique_list(lst: List[str]) -> List[str]:
                seen = set()
                result = []
                for item in lst:
                    cleaned_item = _clean_string(item.strip())
                    if cleaned_item and cleaned_item not in seen:
                        seen.add(cleaned_item)
                        result.append(cleaned_item)
                return result
            
            people = _clean_and_unique_list(people)
            tags = _clean_and_unique_list(tags)
            
        except json.JSONDecodeError:
            # 如果 JSON 解析失败，返回空列表
            pass
            
    except subprocess.TimeoutExpired:
        # 如果 exiftool 超时，返回空列表
        pass
    except Exception:
        # 其他异常，返回空列表
        pass
    
    return people, tags


def extract_people_and_tags(path: str) -> Tuple[List[str], List[str]]:
    """
    使用 ExifTool CLI 获取图片 metadata
    """
    people: List[str] = []
    tags: List[str] = []
    
    # 使用 ExifTool CLI
    if _HAS_EXIFTOOL:
        try:
            people, tags = _from_exiftool_cli(path)
        except Exception:
            pass
    
    return people, tags