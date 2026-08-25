import json
import os
import logging
from zip_operator import zip_read
from logging_setup import configure_logging

archive_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "data.zip")
logger = logging.getLogger(__name__)
def get_version():
    try:
        data = json.loads(zip_read(archive_path, "data.json"))
        return float(data.get("version", "1.1"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return -1.114514

def main():
    configure_logging()
    logger.info("版本查询模块启动")
    logger.info("data.json 中的数据版本：%s", get_version())

if __name__ == "__main__":
    main()
