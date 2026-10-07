# -*- coding: utf-8 -*-
"""插件治理：发现、校验、批准、注册表。

V3.0 插件治理核心。metadata.json 为唯一真值源，
registry 为唯一能力表，旧七类视图从 registry 派生。
"""

from plugin_manager.loader import scan_metadata, scan_plugin_dirs
from plugin_manager.registry import PluginRegistry, RegistrySnapshot, snapshot
from plugin_manager.validator import validate_metadata, validate_entry_point
from plugin_manager.error_reporter import (
    report as report_plugin_error,
    aggregate as aggregate_errors,
    get_recent_errors,
    has_recent_error,
    PluginErrorContext,
)

__all__ = [
    "scan_metadata",
    "scan_plugin_dirs",
    "PluginRegistry",
    "RegistrySnapshot",
    "snapshot",
    "validate_metadata",
    "validate_entry_point",
    # Error reporter exports
    "report_plugin_error",
    "aggregate_errors",
    "get_recent_errors",
    "has_recent_error",
    "PluginErrorContext",
]
