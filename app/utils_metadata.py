import subprocess
import json
from typing import List, Tuple

# ExifTool CLI support (via exiftool.exe available on system PATH)
_HAS_EXIFTOOL = False
try:
    # Probe whether exiftool is available on the system PATH
    result = subprocess.run(['exiftool', '-ver'], capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        _HAS_EXIFTOOL = True
except Exception:
    pass


def has_exiftool() -> bool:
    """Return whether a usable exiftool CLI was detected.
    Detection happens once at process start to avoid frequent subprocess calls.
    """
    return _HAS_EXIFTOOL


def _from_exiftool_cli(path: str) -> Tuple[List[str], List[str]]:
    """Get all metadata using exiftool.exe (from system PATH)."""
    people: List[str] = []
    tags: List[str] = []
    
    if not _HAS_EXIFTOOL:
        return people, tags
    
    try:
        # First attempt: use standard UTF-8 settings
        result = None
        try:
            result = subprocess.run([
                'exiftool', 
                '-json',  # JSON output
                '-all',   # Fetch all metadata
                '-charset', 'utf8',  # Ensure correct character encoding
                '-coordFormat', '%.6f',  # Coordinate format
                '-dateFormat', '%Y:%m:%d %H:%M:%S',  # Date format
                '-escape', 'xml',  # Escape special characters as XML
                '-ignoreMinorErrors',  # Ignore minor errors
                path
            ], capture_output=True, text=True, timeout=30, encoding='utf-8')
        except Exception:
            pass
        
        # If the first attempt fails or returns empty output, try different charset options
        if not result or result.returncode != 0 or not result.stdout.strip():
            try:
                result = subprocess.run([
                    'exiftool', 
                    '-json',
                    '-all',
                    '-charset', 'filename=utf8',  # Use UTF-8 for filenames
                    '-charset', 'exif=utf8',      # Use UTF-8 for EXIF
                    '-charset', 'iptc=utf8',      # Use UTF-8 for IPTC
                    '-charset', 'xmp=utf8',       # Use UTF-8 for XMP
                    '-ignoreMinorErrors',
                    path
                ], capture_output=True, text=True, timeout=30, encoding='utf-8')
            except Exception:
                pass
        
        # If it still fails, try the most basic settings
        if not result or result.returncode != 0:
            try:
                # On Windows we may need to use the system default encoding
                import locale
                system_encoding = locale.getpreferredencoding()
                
                raw_result = subprocess.run([
                    'exiftool', 
                    '-json',
                    '-all',
                    '-charset', system_encoding,  # Use system encoding
                    path
                ], capture_output=True, timeout=30)
                
                # Manually convert bytes to string
                if raw_result.stdout and raw_result.returncode == 0:
                    stdout_text = ""
                    try:
                        # Try decoding as UTF-8
                        stdout_text = raw_result.stdout.decode('utf-8')
                    except UnicodeDecodeError:
                        try:
                            # Try decoding with system encoding
                            stdout_text = raw_result.stdout.decode(system_encoding, errors='replace')
                        except:
                            # Fallback: decode with replacement
                            stdout_text = raw_result.stdout.decode('utf-8', errors='replace')
                    
                    # Create a mock result object
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
        
        # Parse JSON output
        try:
            metadata_list = json.loads(result.stdout)
            if not metadata_list or not isinstance(metadata_list, list):
                return people, tags
            
            metadata = metadata_list[0]  # exiftool returns a list; take the first item
            
            # Extract tags (Keywords)
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
                        # Split string tags (semicolon/comma/other separators)
                        if ';' in value:
                            tags.extend([tag.strip() for tag in value.split(';') if tag.strip()])
                        elif ',' in value:
                            tags.extend([tag.strip() for tag in value.split(',') if tag.strip()])
                        else:
                            tags.append(value.strip())
                    elif isinstance(value, list):
                        # If it's a list, extend directly
                        tags.extend([str(tag).strip() for tag in value if str(tag).strip()])
            
            # Extract people/faces
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
            
            # Special handling: extract people from RegionInfo
            region_info = metadata.get('RegionInfo')
            if region_info and isinstance(region_info, str):
                # Try to parse a possible JSON string
                try:
                    import re
                    # Find name patterns
                    name_pattern = r'"Name"\s*:\s*"([^"]+)"'
                    matches = re.findall(name_pattern, region_info)
                    people.extend([name.strip() for name in matches if name.strip()])
                except Exception:
                    pass
            
            # String cleanup function to handle encoding issues
            def _clean_string(s: str) -> str:
                """Clean a string and handle potential encoding issues."""
                if not s:
                    return s
                
                # Try to fix common encoding problems
                try:
                    # Special handling: check for common Windows ExifTool encoding issues
                    # In such cases, Chinese characters might be mis-encoded
                    
                    # Method 1: check for obvious mojibake characters
                    # Typical mojibake patterns: specific Unicode ranges/characters
                    suspicious_chars = any(
                        0x4E00 <= ord(c) <= 0x9FFF and  # CJK Unified Ideographs
                        c in '闄堝啺濂囧鍋夸奇妙妈妹' for c in s  # Common mojibake chars
                    )
                    
                    if suspicious_chars:
                        # Likely encoding issue; drop this string
                        return ""
                    
                    # Method 2: try re-encoding fixes
                    # Windows EXIF data sometimes needs special handling
                    try:
                        # Try to handle potential CP936 (GBK) related issues
                        if any(ord(c) > 127 for c in s):
                            # Contains non-ASCII characters; may need fixing
                            # Attempt reverse-engineering of a wrongly decoded string
                            
                            # Check if UTF-8 bytes might have been decoded with a different single-byte codec
                            for source_encoding in ['cp1252', 'iso-8859-1']:
                                for target_encoding in ['utf-8', 'gbk', 'gb2312']:
                                    try:
                                        # Attempt a reverse-repair
                                        temp_bytes = s.encode(source_encoding, errors='ignore')
                                        if temp_bytes:
                                            fixed = temp_bytes.decode(target_encoding, errors='ignore')
                                            if fixed and fixed != s and len(fixed) > 0:
                                                # Validate the fix (contains plausible Chinese characters)
                                                if any(0x4E00 <= ord(c) <= 0x9FFF for c in fixed):
                                                    return fixed
                                    except:
                                        continue
                    except:
                        pass
                    
                    # Method 3: if it contains obviously invalid characters, filter them out
                    filtered_chars = []
                    for c in s:
                        code = ord(c)
                        # Keep reasonable character ranges
                        if (32 <= code <= 126) or \
                           (0x4E00 <= code <= 0x9FFF) or \
                           (0x3400 <= code <= 0x4DBF) or \
                           (0x20000 <= code <= 0x2A6DF) or \
                           code in [0x3000, 0xFF01, 0xFF1A, 0xFF1B, 0xFF1F]:  # Common Chinese punctuation
                            filtered_chars.append(c)
                    
                    filtered_s = ''.join(filtered_chars)
                    if filtered_s != s and len(filtered_s) > 0:
                        return filtered_s
                        
                except Exception:
                    pass
                
                # If all repair attempts fail, return the original string
                return s
            
            # Clean people and tags lists
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
            # If JSON parsing fails, return empty lists
            pass
            
    except subprocess.TimeoutExpired:
        # If exiftool times out, return empty lists
        pass
    except Exception:
        # Other exceptions: return empty lists
        pass
    
    return people, tags


def extract_people_and_tags(path: str) -> Tuple[List[str], List[str]]:
    """
    Extract image metadata using ExifTool CLI.
    """
    people: List[str] = []
    tags: List[str] = []
    
    # Use ExifTool CLI
    if _HAS_EXIFTOOL:
        try:
            people, tags = _from_exiftool_cli(path)
        except Exception:
            pass
    
    return people, tags