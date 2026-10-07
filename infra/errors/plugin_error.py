# -*- coding: utf-8 -*-
"""
插件错误上下文（V3.0）
=====================

结构化捕获插件异常信息，便于主干监控和问题定位。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ErrorType(Enum):
    """插件错误类型分类。"""
    USER_ERROR = "user_error"         # 用户配置错误、数据格式错误
    NETWORK_ERROR = "network_error"   # HTTP/连接/DNS 错误
    DATA_ERROR = "data_error"         # 处理数据时失败，schema 不匹配
    CONTRACT_ERROR = "contract_error" # 违反契约（返回类型、必填字段缺失）


@dataclass
class PluginErrorContext:
    """插件异常的结构化上下文。

    主干捕获后写入 context.errors，支持从插件 metadata.json 中读取
    on_error 策略（skip / retry / halt）。
    """
    plugin_name: str                    # 插件实例名
    plugin_version: str                 # 插件版本
    stage: str                          # acquire / process / store / present
    input_dto: dict[str, Any]           # 脱敏后的输入快照
    traceback_full: str                 # 完整的 traceback 文本（不包含凭据）
    error_type: ErrorType               # 错误类型分类
    suggestion: str                     # 主干侧根据 error_type 给出的修复方向
    on_error: str = "skip"              # 插件 metadata 中声明的策略
    retry_count: int = 0                # 当前重试次数
    retry_policy: Optional[dict] = None # 重试策略（若配置）

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_name": self.plugin_name,
            "plugin_version": self.plugin_version,
            "stage": self.stage,
            "input_dto": self.input_dto,
            "traceback_full": self.traceback_full,
            "error_type": self.error_type.value,
            "suggestion": self.suggestion,
            "on_error": self.on_error,
            "retry_count": self.retry_count,
            "retry_policy": self.retry_policy,
        }


def get_suggestion(error_type: ErrorType) -> str:
    """根据错误类型返回主干侧的修复建议。"""
    suggestions = {
        ErrorType.USER_ERROR: "检查插件配置项、输入数据格式及目标 URL 正确性；或检查上游 spider 返回的 URL 列表是否包含无效链接。",
        ErrorType.NETWORK_ERROR: "检查网络连通性、目标域名 DNS 解析、站点是否临时不可达；可考虑增大 timeout 或暂停该域名爬取。",
        ErrorType.DATA_ERROR: "检查输入数据 schema 是否符合插件声明的 input_schema；或检查字段映射、数据清洗规则。",
        ErrorType.CONTRACT_ERROR: "检查插件是否返回符合 output_schema 的 DTO；或检查字段类型、必填项缺失。",
    }
    return suggestions.get(error_type, "查看完整 traceback 定位问题根源。")


def classify_error_type(error: Exception, stage: str) -> ErrorType:
    """根据异常类型和阶段判断错误类型。"""
    from infra.errors import classify_http_error

    # HTTP 相关错误属于 network_error
    if stage in ("acquire", "process"):
        http_code = classify_http_error(error)
        if http_code.startswith("HTTP_"):
            return ErrorType.NETWORK_ERROR

    # Schema/字段相关错误属于 contract_error
    error_msg = str(error).lower()
    if "schema" in error_msg or "contract" in error_msg:
        return ErrorType.CONTRACT_ERROR

    # 数据处理相关错误属于 data_error
    if stage in ("process", "store"):
        if "validation" in error_msg or "field" in error_msg or "missing" in error_msg:
            return ErrorType.DATA_ERROR

    # 默认返回 user_error
    return ErrorType.USER_ERROR
