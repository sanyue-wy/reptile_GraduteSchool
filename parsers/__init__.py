# -*- coding: utf-8 -*-
"""
Parser 插件注册表
=================
每种公示/专业目录模板对应一个 parser 文件。
约定接口：parse(raw_path: str, meta: dict) -> list[dict]

使用方式：
    from parsers import dispatch

    meta = {"template": "yzw_major", "university": "东南大学", ...}
    records = dispatch("data/raw/.../major_10213.json", meta)
"""

import logging
from typing import Callable, Dict, List

logger = logging.getLogger(__name__)

# 注册表：template 名 → parse 函数
_REGISTRY: Dict[str, Callable[[str, Dict], List[Dict]]] = {}


def register(template_name: str):
    """装饰器，注册 parser 函数到注册表。

    Args:
        template_name: 模板名称，对应配置中 notice.template 的值
    """
    def decorator(func: Callable[[str, Dict], List[Dict]]):
        if template_name in _REGISTRY:
            logger.warning("Parser '%s' 已注册，将被覆盖", template_name)
        _REGISTRY[template_name] = func
        return func
    return decorator


def dispatch(raw_path: str, meta: Dict) -> List[Dict]:
    """
    统一入口：根据 meta["template"] 路由到对应 parser。

    Args:
        raw_path: 原件文件路径
        meta: 含 template 字段的元数据

    Returns:
        List[Dict] 解析结果

    Raises:
        ValueError: template 未注册或 meta 缺少 template 字段
    """
    template = meta.get("template", "")
    if not template:
        raise ValueError(f"meta 中缺少 template 字段: {meta}")

    parser_fn = _REGISTRY.get(template)
    if not parser_fn:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(f"未注册的 parser template: '{template}'，可用: {available}")

    logger.info("Dispatching parser '%s' for %s/%s", template, meta.get('university', '?'), meta.get('college', '?'))
    return parser_fn(raw_path, meta)


def list_registered() -> List[str]:
    """返回所有已注册的 template 名称列表（排序后）。"""
    return sorted(_REGISTRY.keys())


# 自动导入 parser 子模块，触发 @register 装饰器
# 顺序：按复杂度升序，避免循环依赖
from . import yzw_major  # noqa: E402,F401
