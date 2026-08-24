import json
import os
import logging
from zip_operator import zip_read

archive_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "data.zip")
logger = logging.getLogger(__name__)
def get_version():
    try:
        data = json.loads(zip_read(archive_path, "data.json"))
        return float(data.get("version", "1.1"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return -1.114514

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(threadName)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("版本查询模块启动")
    logger.info("data.json 中的数据版本：%s", get_version())

if __name__ == "__main__":
    main()
