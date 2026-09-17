# -*- coding: utf-8 -*-
"""
SpiderEngine 抽象基类测试
========================
覆盖 docs/V2.2/agents/agent-c-spider.md Step 1 的冻结接口契约：
- 抽象基类不能直接实例化
- 子类通过构造函数注入 session / cache
- register_engine 装饰器返回原类并注册到 ENGINE_REGISTRY
- __repr__ 输出
- 测试结束后恢复 ENGINE_REGISTRY，不污染真实注册表
"""

import pytest

from spiders.engine import SpiderEngine, ENGINE_REGISTRY, register_engine


@pytest.fixture
def restore_registry():
    """快照 ENGINE_REGISTRY，测试结束后恢复，避免污染真实数据。"""
    snapshot = dict(ENGINE_REGISTRY)
    yield ENGINE_REGISTRY
    ENGINE_REGISTRY.clear()
    ENGINE_REGISTRY.update(snapshot)


class DummyEngine(SpiderEngine):
    """最小实现子类，用于验证接口契约。"""

    name = "dummy_test_engine"
    supported_source = "source_a"

    def fetch(self, url, **kwargs):
        return [{"url": url, **kwargs}]

    def parse(self, html, selectors, **kwargs):
        return [{"html": html, "selectors": selectors}]


class TestAbstractBaseClass:
    def test_cannot_instantiate_abstract_class(self):
        """SpiderEngine 含抽象方法，不能直接实例化。"""
        with pytest.raises(TypeError):
            SpiderEngine(session=object())

    def test_abstract_methods_declared(self):
        """fetch 与 parse 均为抽象方法。"""
        assert getattr(SpiderEngine.fetch, "__isabstractmethod__", False) is True
        assert getattr(SpiderEngine.parse, "__isabstractmethod__", False) is True

    def test_incomplete_subclass_cannot_instantiate(self):
        """只实现 fetch 不实现 parse 的子类同样不能实例化。"""

        class PartialEngine(SpiderEngine):
            name = "partial"
            supported_source = "source_b"

            def fetch(self, url, **kwargs):
                return []

        with pytest.raises(TypeError):
            PartialEngine(session=object())


class TestDependencyInjection:
    def test_constructor_injects_session_and_cache(self, mock_cache):
        session = object()
        engine = DummyEngine(session, cache=mock_cache)
        assert engine.session is session
        assert engine.cache is mock_cache

    def test_cache_defaults_to_none(self):
        session = object()
        engine = DummyEngine(session)
        assert engine.session is session
        assert engine.cache is None

    def test_class_attributes(self):
        assert DummyEngine.name == "dummy_test_engine"
        assert DummyEngine.supported_source == "source_a"
        engine = DummyEngine(object())
        assert engine.name == "dummy_test_engine"
        assert engine.supported_source == "source_a"

    def test_fetch_and_parse_dispatch(self):
        engine = DummyEngine(object())
        assert engine.fetch("http://test.edu.cn", force=True) == [
            {"url": "http://test.edu.cn", "force": True}
        ]
        assert engine.parse("<html></html>", {".name": ".name"}) == [
            {"html": "<html></html>", "selectors": {".name": ".name"}}
        ]


class TestRegisterEngineDecorator:
    def test_decorator_returns_original_class(self, restore_registry):
        @register_engine
        class DecoratedEngine(SpiderEngine):
            name = "decorated_test_engine"
            supported_source = "source_b"

            def fetch(self, url, **kwargs):
                return []

            def parse(self, html, selectors, **kwargs):
                return []

        assert DecoratedEngine is not None
        assert issubclass(DecoratedEngine, SpiderEngine)
        assert DecoratedEngine.name == "decorated_test_engine"

    def test_registered_engine_fetch_returns_records(self, restore_registry):
        registered = register_engine(DummyEngine)
        assert registered is DummyEngine
        session = object()
        engine = ENGINE_REGISTRY[DummyEngine.name](session)
        assert engine.session is session
        assert engine.fetch("https://example.com/faculty", force=True) == [
            {"url": "https://example.com/faculty", "force": True}
        ]

    def test_decorator_registers_into_registry(self, restore_registry):
        @register_engine
        class AnotherEngine(SpiderEngine):
            name = "another_test_engine"
            supported_source = "source_a"

            def fetch(self, url, **kwargs):
                return []

            def parse(self, html, selectors, **kwargs):
                return []

        assert ENGINE_REGISTRY["another_test_engine"] is AnotherEngine

    def test_registry_restore_on_exit(self, restore_registry):
        marker = "restore_probe_engine"

        @register_engine
        class ProbeEngine(SpiderEngine):
            name = marker
            supported_source = "source_a"

            def fetch(self, url, **kwargs):
                return []

            def parse(self, html, selectors, **kwargs):
                return []

        assert marker in ENGINE_REGISTRY
        # fixture teardown 会恢复；此处手动模拟恢复后验证
        ENGINE_REGISTRY.pop(marker, None)
        assert marker not in ENGINE_REGISTRY


class TestRepr:
    def test_repr_format(self):
        engine = DummyEngine(object())
        assert repr(engine) == "<DummyEngine name='dummy_test_engine'>"

    def test_repr_contains_class_name_and_name(self):
        engine = DummyEngine(object())
        text = repr(engine)
        assert "DummyEngine" in text
        assert "dummy_test_engine" in text


class TestExistingFunctionRegistryUntouched:
    def test_spiders_init_function_registry_not_overwritten(self):
        """spiders/__init__.py 的函数注册表（list_type → 函数）必须保持原样。"""
        from spiders import ENGINE_REGISTRY as FUNC_REGISTRY

        assert "static_html" in FUNC_REGISTRY
        assert "ajax_api" in FUNC_REGISTRY
        assert callable(FUNC_REGISTRY["static_html"])
        # 两个注册表相互独立
        assert FUNC_REGISTRY is not ENGINE_REGISTRY

    def test_six_engines_registered_and_legacy_table_exact(self):
        import inspect
        import spiders
        expected = {"static_list", "ajax_api", "yzw_api", "detail_parser", "js_render", "pdf_list"}
        assert set(ENGINE_REGISTRY) == expected
        assert spiders.SPIDER_ENGINE_REGISTRY is ENGINE_REGISTRY
        assert spiders.ENGINE_REGISTRY == {
            "static_html": spiders.fetch_faculty_list,
            "ajax_api": spiders.fetch_faculty_via_api,
            "js_render": spiders.fetch_faculty_via_playwright,
            "pdf_list": spiders.parse_pdf_faculty_list,
        }
        for name, cls in ENGINE_REGISTRY.items():
            assert issubclass(cls, SpiderEngine) and not inspect.isabstract(cls)
            instance = cls(object())
            assert instance.name == name
            assert instance.supported_source in ("source_a", "source_b")
            assert callable(instance.fetch) and callable(instance.parse)


def test_static_engine_real_fetch_parse_cache(offline_transport, mock_cache):
    from spiders import StaticListEngine
    session, routes, calls = offline_transport
    url = "https://offline.invalid/faculty"
    html = '<ul><li><a title="张三" href="/people/1">张三</a></li></ul>'
    routes[url] = html
    engine = StaticListEngine(session, mock_cache)
    selectors = {"item": "li a", "name": "title", "profile": "href"}
    expected = engine.parse(html, selectors, base_url=url)
    assert len(expected) == 1 and expected[0]["name"] == "张三"
    assert expected[0]["profile_url"] == "https://offline.invalid/people/1"
    assert engine.fetch(url, selectors=selectors) == expected
    assert engine.fetch(url, selectors=selectors) == expected
    assert len(calls) == 1
    assert engine.fetch(url, selectors=selectors, force=True) == expected
    assert len(calls) == 2


def test_ajax_engine_real_fetch_and_parse(offline_transport, mock_cache):
    import json
    from spiders import AjaxApiEngine
    session, routes, calls = offline_transport
    url = "https://offline.invalid/api"
    data = {"total": 1, "data": [{"title": "张三", "post": "教授", "cnUrl": "/people/1"}]}
    routes[url] = data
    engine = AjaxApiEngine(session, mock_cache)
    expected = engine.parse(json.dumps(data), {}, api_url=url)
    assert len(expected) == 1 and expected[0]["name"] == "张三"
    assert engine.fetch(url, site_id="42", referer="https://offline.invalid/") == expected
    assert len(calls) == 1
    assert calls[0][2]["data"]["siteId"] == "42"


def test_detail_engine_wraps_legacy_dict(offline_transport):
    from spiders import DetailParserEngine, fetch_detail
    session, routes, _ = offline_transport
    url = "https://offline.invalid/people/1"
    html = '<div class="carrer"><div class="title"><span class="jsbt">张三</span>教授 博士生导师</div></div>'
    routes[url] = html
    engine = DetailParserEngine(session)
    expected = engine.parse(html, {}, profile_url=url)
    assert expected[0]["title"] == "教授"
    assert engine.fetch(url) == expected == [fetch_detail(session, url)]

