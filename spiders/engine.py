# -*- coding: utf-8 -*-
"""
爬虫引擎抽象基类
================

统一 5 个爬虫引擎的接口，降低 spiders/ 间直接依赖，
为未来插件化爬虫打基础（docs/V2.2/agents/agent-c-spider.md）。

用法::

    @register_engine
    class StaticListEngine(SpiderEngine):
        name = "static_list"
        supported_source = "source_a"

        def fetch(self, url, **kwargs) -> list[dict]:
            ...

        def parse(self, html, selectors, **kwargs) -> list[dict]:
            ...

注意：spiders/__init__.py 中另有按 list_type 分派的函数注册表
（ENGINE_REGISTRY: str → 获取函数），与本模块的引擎类注册表
（str → SpiderEngine 子类）相互独立、互不影响。
"""

from abc import ABC, abstractmethod
from typing import Optional

from utils.cache import CrawlCache
from utils.http import PoliteSession


class SpiderEngine(ABC):
    """所有爬虫引擎的抽象基类。

    子类只需声明 ``name`` 与 ``supported_source`` 两个类属性，
    并实现 :meth:`fetch` 与 :meth:`parse`；session 与 cache
    由构造函数注入。
    """

    name: str = ""
    supported_source: str = ""  # "source_a" / "source_b"

    def __init__(self, session: PoliteSession, cache: Optional[CrawlCache] = None):
        self.session = session
        self.cache = cache

    @abstractmethod
    def fetch(self, url: str, **kwargs) -> list[dict]:
        """抓取并解析，返回教师/专业记录列表。kwargs 传递引擎特定参数。"""

    @abstractmethod
    def parse(self, html: str, selectors: dict, **kwargs) -> list[dict]:
        """解析 HTML/JSON，返回记录列表。"""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"


# 引擎注册表：name → SpiderEngine 子类（独立于 spiders/__init__.py 的函数注册表）
ENGINE_REGISTRY: dict[str, type[SpiderEngine]] = {}


def register_engine(cls: type[SpiderEngine]) -> type[SpiderEngine]:
    """注册引擎类到全局注册表，并原样返回该类。

    以 ``cls.name`` 为键；与 spiders/__init__.py 的函数注册表独立。
    """
    ENGINE_REGISTRY[cls.name] = cls
    return cls
