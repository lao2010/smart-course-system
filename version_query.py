# -*- coding: utf-8 -*-

import json
import os
import logging
from zip_operator import zip_read
from logging_setup import configure_logging

archive_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "data.zip")
logger = logging.getLogger("版本查询")
def get_version():
    try:
        raw = zip_read(archive_path, "data.json")
        if raw is None:
            # data.zip 缺失/损坏（如新装机未首次同步）：返回哨兵负版本，
            # 触发同步服务从节点下载——此前 None.decode 抛 AttributeError
            # 落在捕获列表之外，导致新装机永远进不了版本比较（首次同步死锁）
            return -1.114514
        data = json.loads(raw.decode("utf-8"))
        return float(data.get("version", "1.1"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return -1.114514

def main():
    configure_logging()
    logger.info("版本查询模块启动")
    logger.info("data.json 中的数据版本：%s", get_version())

if __name__ == "__main__":
    main()
