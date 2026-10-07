# -*- coding: utf-8 -*-
"""
URL Normalizer Processor Plugin
================================
Normalizes URLs with Chinese domain names to their official English abbreviations.

Input: TaskConfigDTO with target_url potentially containing Chinese domain
Output: TaskConfigDTO with target_url corrected, metadata["url_corrected"] = True
"""

import json
import logging
import re
from dataclasses import field, dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from contracts.asset import MediaAsset
from contracts.raw import RawDataBatch, RawDataDTO
from contracts.result import ErrorDTO, StageResult
from contracts.record import RecordBatch, NormalizedRecordDTO
from contracts.task import TaskConfigDTO
from plugins.base import BasePlugin, PluginContext

logger = logging.getLogger(__name__)

_DOMAIN_KB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "domain_kb.json"


class UrlNormalizerProcessor(BasePlugin):
    """Normalize URLs with Chinese domain names to official abbreviations.

    Input:  TaskConfigDTO with target_url containing Chinese domain
    Output: TaskConfigDTO with corrected target_url and url_corrected=True
    """

    name = "url_normalizer"
    version = "1.0.0"
    plugin_type = "processor"
    input_schema = "TaskConfigDTO.v1"
    output_schema = "TaskConfigDTO.v1"

    def __init__(self):
        super().__init__()
        self._domain_kb = self._load_domain_kb()

    def _load_domain_kb(self) -> dict:
        try:
            with open(_DOMAIN_KB_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load domain_kb.json: %s", e)
            return {"mappings": {}}

    def execute(self, data: TaskConfigDTO, context: PluginContext) -> TaskConfigDTO:
        target_url = data.target_url
        parsed = urlparse(target_url)
        hostname = parsed.hostname or ""

        url_corrected = False
        corrected_hostname = hostname

        # Fix double punycode: count xn-- occurrences
        if hostname.count("xn--") >= 2:
            logger.info("Detected double punycode in %s, attempting fix", hostname)
            corrected_hostname = self._fix_double_punycode(hostname)

        if not corrected_hostname:
            corrected_hostname = hostname

        # Match Chinese domain pattern: {sub}.{Chinese}.edu.cn or all-Chinese .edu.cn
        # Subdomain is ASCII (a-z0-9-) OR CJK chars (e.g. 东北.东北.edu.cn); supports
        # parentheses (fullwidth and halfwidth) in university names.
        chinese_pattern = re.compile(
            r"^(?:[a-z0-9-]+|[一-鿿]+)\.([一-鿿　-（）()]+)\.edu\.cn$",
            re.IGNORECASE
        )
        match = chinese_pattern.match(corrected_hostname)

        if match:
            chinese_name = match.group(1)
            school_name = self._extract_school_name(data, chinese_name)

            if school_name and school_name in self._domain_kb.get("mappings", {}):
                mapping = self._domain_kb["mappings"][school_name]
                main_domain = mapping.get("main", "")

                if main_domain:
                    first = corrected_hostname.split(".")[0]
                    # 全中文域名（无 ASCII 子域）直接用主域
                    if not first.isascii():
                        corrected_hostname = main_domain
                    else:
                        # 子域前缀与主域重复时省略（如 cau.中国农业.edu.cn → cau.edu.cn）
                        base = main_domain.split(".")[0]
                        prefix = f"{first}." if first != base else ""
                        corrected_hostname = f"{prefix}{main_domain}"
                    url_corrected = True
                    logger.info("Corrected URL: %s -> %s", hostname, corrected_hostname)

        # Build corrected URL
        if url_corrected and corrected_hostname != hostname:
            corrected_url = re.sub(r"^https?://[^/]+", f"https://{corrected_hostname}", target_url)
            object.__setattr__(data, 'target_url', corrected_url)

            # Set metadata flag
            if not hasattr(data, 'metadata'):
                object.__setattr__(data, 'metadata', {})
            if hasattr(data, 'metadata') and isinstance(data.metadata, dict):
                data.metadata["url_corrected"] = True
                data.metadata["original_url"] = target_url

        return data

    def _fix_double_punycode(self, hostname: str) -> str:
        """Attempt to fix double punycode encoded domains."""
        try:
            import idna
            parts = hostname.split(".")
            decoded_parts = []
            for part in parts:
                if part.startswith("xn--"):
                    try:
                        decoded_parts.append(idna.decode(part))
                    except Exception:
                        decoded_parts.append(part)
                else:
                    decoded_parts.append(part)
            recovered = ".".join(decoded_parts)
            logger.debug("Double punycode recovery: %s -> %s", hostname, recovered)
            return recovered
        except ImportError:
            pass
        return hostname

    def _extract_school_name(self, data: TaskConfigDTO, chinese_domain: str) -> Optional[str]:
        """Extract school name from TaskConfigDTO.

        匹配优先级：显式字段（school / config_snapshot.school）→ university 字段精确/模糊匹配
        → 域名包含关系兜底。含括号校名（如 中国地质大学（北京））按去括号核心名匹配。
        """
        if hasattr(data, 'school') and data.school:
            return data.school
        if data.config_snapshot.get('school'):
            return data.config_snapshot['school']

        uni = data.config_snapshot.get('university') or ""
        if uni:
            if uni in self._domain_kb.get("mappings", {}):
                return uni
            # 模糊匹配：去括号后比较，避免全角/半角括号差异导致失配
            core_uni = re.sub(r"[（(].*?[）)]", "", uni)
            for school_name in self._domain_kb.get("mappings", {}).keys():
                core_kb = re.sub(r"[（(].*?[）)]", "", school_name)
                if core_uni == core_kb or core_kb in chinese_domain:
                    return school_name

        for school_name, mapping in self._domain_kb.get("mappings", {}).items():
            if school_name in chinese_domain or mapping.get("main", "") in chinese_domain:
                return school_name
        return None
