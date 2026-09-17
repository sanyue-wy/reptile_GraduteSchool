# -*- coding: utf-8 -*-
"""插件静态校验接口；不是安全沙箱。"""

from .plugin_validator import ValidationResult, validate_plugin_file, validate_plugin_source

__all__ = ["ValidationResult", "validate_plugin_source", "validate_plugin_file"]
