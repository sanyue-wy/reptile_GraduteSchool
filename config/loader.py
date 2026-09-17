"""配置加载器

负责学校配置的加载、查询、保存和重新加载。
配置文件默认为 config/school_data.json。
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from copy import deepcopy
from storage import ConfigStore, path_lock
from config.validator import validate_school_config

logger = logging.getLogger(__name__)

# 默认配置文件路径
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "school_data.json"

# 内存缓存
_config_cache: Optional[List[Dict]] = None
_config_path: Path = DEFAULT_CONFIG_PATH


def _resolve_path(path: Optional[str] = None) -> Path:
    """解析配置文件路径"""
    if path is None:
        return _config_path
    return Path(path)


def load_schools_config(path: Optional[str] = None) -> List[Dict]:
    """
    加载全量学校配置。

    Args:
        path: 配置文件路径，默认 config/school_data.json

    Returns:
        List[Dict]  # 每项符合 INTERFACE_SPEC.md 第 4 节配置结构
        必含字段：university, categories[{college, category, faculty, notice}]

    行为：
        1. 读取配置文件
        2. 自动填充 level（从 school_level_raw 推导）
        3. 验证必填字段（调用 validate_school_config）
        4. 验证失败的条目记录 warning 但不中断加载
    """
    global _config_cache, _config_path
    config_path = _resolve_path(path)
    _config_path = config_path

    if not config_path.exists():
        logger.warning("配置文件不存在: %s，尝试从 schools.py 读取", config_path)
        # Fallback: 从旧的 schools.py 加载
        try:
            from config.schools import SCHOOLS_CONFIG
            configs = SCHOOLS_CONFIG
        except ImportError:
            logger.error("config.schools 也不可用，使用空配置")
            return []
    else:
        configs = ConfigStore(config_path=config_path).load_schools()

    # 填充 level 字段（如果缺失）
    try:
        from config.school_level_raw import get_school_level, validate_and_fix_levels

        validate_and_fix_levels()  # 确保 985 ⊂ 211 ⊂ 双一流

        for cfg in configs:
            if not cfg.get("level"):
                cfg["level"] = get_school_level(cfg.get("university", ""))
    except ImportError:
        logger.warning("无法导入 school_level_raw，跳过 level 填充")

    # 验证必填字段（记录 warning，不中断）
    for cfg in configs:
        errors = validate_school_config(cfg)
        for err in errors:
            logger.warning("配置校验: %s", err)

    _config_cache = configs
    return configs


def get_school_config(university: str) -> Optional[Dict]:
    """
    按校名查找单校配置。

    Returns:
        Dict | None  # 符合 INTERFACE_SPEC.md 4 节结构，未找到返回 None
    """
    global _config_cache
    if _config_cache is None:
        _config_cache = load_schools_config()

    for cfg in _config_cache:
        if cfg.get("university") == university:
            return cfg
    return None


def save_school_config(university: str, config: Dict) -> bool:
    """
    保存单校配置（API `/api/config/schools/{name}` PUT 调用）。

    Args:
        university: 学校标准名
        config: 完整校配置对象

    Returns:
        bool: 是否保存成功

    行为：
        1. 校验 config 合法性
        2. 更新内存缓存
        3. 原子写入配置文件
    """
    global _config_cache, _config_path

    # 1. 校验
    errors = validate_school_config(config)
    if errors:
        logger.error("保存学校 %s 配置失败，校验错误: %s", university, [str(e) for e in errors])
        return False

    # Persist before publishing the cache; failed writes leave both untouched.
    store = ConfigStore(config_path=_config_path)
    with path_lock(_config_path):
        if not store.save_school(university, config):
            return False
        _config_cache = store.load_schools()
    logger.info("保存学校 %s 配置到 %s", university, _config_path)
    return True


def reload_config() -> int:
    """
    重新加载配置文件（API `/api/config/global` PUT 后调用）。

    Returns:
        int: 加载的学校数量
    """
    global _config_cache
    _config_cache = load_schools_config()
    logger.info("重新加载配置，共 %d 所学校", len(_config_cache))
    return len(_config_cache)
