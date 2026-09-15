# -*- coding: utf-8 -*-
"""
统一日志配置
============
"""

import logging
import sys
from pathlib import Path


def setup_logging(level: str = "INFO", log_file: str = "data/output/crawl.log"):
    """
    统一日志配置。

    输出：
        - 控制台：INFO 及以上，简洁格式
        - 文件：DEBUG 及以上，含时间戳和模块名
    """
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(getattr(logging, level.upper()))
    console.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

    # 文件
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console)
    root.addHandler(file_handler)

    # 降低第三方库日志级别
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
