import os
import tempfile
from zipfile import ZipFile
from zipfile import BadZipFile
def zip_read(zip, file_path):
    """从压缩包中读取文件内容"""
    try:
        with ZipFile(zip) as archive:
            with archive.open(file_path) as file:
                return file.read()
    except (FileNotFoundError, BadZipFile, KeyError):
        return None

def zip_check(zip_path):
    """检查压缩包是否有效"""
    try:
        with ZipFile(zip_path) as archive:
            return archive.testzip() is None
    except (FileNotFoundError, BadZipFile, OSError):
        return False

def zip_change_file(zip, file_path, new_content):
    """替换压缩包中的文件内容"""
    temp_path = None
    try:
        # “a”模式只是追加，可能产生同名条目，不能真正替换文件。
        with ZipFile(zip, 'r') as source:
            with tempfile.NamedTemporaryFile(
                dir=os.path.dirname(os.path.abspath(zip)),
                suffix='.zip',
                delete=False,
            ) as temp:
                temp_path = temp.name

            with ZipFile(temp_path, 'w') as target:
                for info in source.infolist():
                    if info.filename != file_path:
                        target.writestr(info, source.read(info.filename))
                target.writestr(file_path, new_content)

        os.replace(temp_path, zip)
    except (FileNotFoundError, BadZipFile, OSError):
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        return False
    return True