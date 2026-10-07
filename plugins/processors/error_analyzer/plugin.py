# -*- coding: utf-8 -*-
"""
Error Analyzer Plugin
=====================
Processor plugin: RawDataDTO → RecordBatch.

Analyzes failures.json content and provides diagnosis patterns:
  a. url_has_chinese_domain：URL 含中文 + .edu.cn
  b. double_punycode：url.count("xn--") >= 2
  c. real_dns_failure：dns_error 且 URL 无中文
  d. path_404：http_error + "404" in message
  e. slow_server：timeout

Each failure record outputs:
  - diagnosis
  - suggested_fix
  - severity
  - counter_summary (written to logs + metadata)
"""

import hashlib
import json
import logging
import re
from collections import Counter
from datetime import datetime
from typing import Any, Optional

from contracts.record import NormalizedRecordDTO, RecordBatch
from contracts.profiles.education import EDUCATION_TUTOR_V1
from plugins.base import RecordProcessorPlugin

logger = logging.getLogger(__name__)

# Chinese character detection
CHINESE_PATTERN = re.compile(r"[一-鿿]")
PUNYCODE_PATTERN = re.compile(r"xn--")
EDUCN_PATTERN = re.compile(r"\.edu\.cn", re.IGNORECASE)


def has_chinese(text: str) -> bool:
    return bool(CHINESE_PATTERN.search(text))


def count_punycode(url: str) -> int:
    return len(PUNYCODE_PATTERN.findall(url))


def is_edu_cn(url: str) -> bool:
    return bool(EDUCN_PATTERN.search(url))


DIAGNOSIS_PATTERNS = {
    "url_has_chinese_domain": {
        "check": lambda f: (
            f.get("error_type") == "dns_error" and
            is_edu_cn(f.get("url", ""))
        ),
        "suggested_fix": "URL is a .edu.cn domain with DNS failure. This indicates Chinese university domain that DNS resolvers cannot resolve - likely punycode encoding or DNS hijacking.",
        "severity": "high",
    },
    "double_punycode": {
        "check": lambda f: count_punycode(f.get("url", "")) >= 2,
        "suggested_fix": "Double-encoded punycode detected. Check for double-encoding bug in URL construction or browser redirect handling.",
        "severity": "medium",
    },
    "real_dns_failure": {
        "check": lambda f: (
            f.get("error_type") == "dns_error" and
            not is_edu_cn(f.get("url", ""))
        ),
        "suggested_fix": "DNS resolution failed for non-.edu.cn domain. Likely network issue or domain genuinely does not exist. Check DNS settings and retry later.",
        "severity": "medium",
    },
    "path_404": {
        "check": lambda f: (
            f.get("error_type") == "http_error" and
            "404" in str(f.get("error_message", ""))
        ),
        "suggested_fix": "Page not found (404). URL may be outdated or resource was moved/deleted. Verify URL pattern or retry without pagination endpoint.",
        "severity": "low",
    },
    "slow_server": {
        "check": lambda f: f.get("error_type") == "timeout",
        "suggested_fix": "Server response timeout. Consider increasing timeout threshold or reducing request rate. May indicate server overload.",
        "severity": "medium",
    },
}


class ErrorAnalyzerPlugin(RecordProcessorPlugin):
    """Analyze failures and provide diagnosis with suggested fixes."""

    name = "error_analyzer"
    version = "1.0.0"
    plugin_type = "processor"
    input_schema = "RecordBatch.v1"
    output_schema = "RecordBatch.v1"

    def setup(self, context) -> None:
        self._params = context.config_snapshot.get("plugins", {}).get("error_analyzer", {}).get("params", {})

    def execute(self, record_batch: RecordBatch, context) -> RecordBatch:
        """Analyze failures and return RecordBatch with diagnosis records."""
        self.setup(context)

        # Extract failures from context.config_snapshot (e.g., from failures.json)
        failures = self._extract_failures_from_context(context)
        if not failures:
            return RecordBatch(
                schema_version="1",
                records=[],
                stats={"analyzer_total": 0, "diagnoses": {}},
                errors=[],
            )

        cfg = context.config_snapshot
        university = cfg.get("university", "")
        college = cfg.get("college", "")
        year = cfg.get("year", 0)

        analyzed_records: list[NormalizedRecordDTO] = []
        counter = Counter()

        for failure in failures:
            diagnosis = self._diagnose_failure(failure)
            suggested_fix = self._suggest_fix(failure, diagnosis)
            severity = self._assess_severity(failure, diagnosis)

            counter[diagnosis or "unknown"] += 1

            fields = {
                "university": university,
                "college": college,
                "category": cfg.get("category", ""),
                "year": year,
                "school": failure.get("school", ""),
                "name": failure.get("college", ""),
                "error_type": failure.get("error_type", ""),
                "url": failure.get("url", ""),
                "error_message": failure.get("error_message", ""),
                "diagnosis": diagnosis,
                "suggested_fix": suggested_fix,
                "severity": severity,
                "source": failure.get("source", ""),
            }

            record_id = hashlib.sha256(
                f"{failure.get('id', '')}".encode("utf-8")
            ).hexdigest()[:32]

            analyzed_records.append(NormalizedRecordDTO(
                record_id=record_id,
                dataset=f"{university}:{college}",
                schema_id=EDUCATION_TUTOR_V1,
                fields=fields,
                provenance={"source_id": failure.get("source_id", ""), "fetched_at": failure.get("occurred_at", "")},
            ))

        # Log counter summary
        total = sum(counter.values())
        counter_dict = dict(counter)
        logger.info("Error analyzer: processed %d failures", total)
        for diag, count in sorted(counter_dict.items()):
            logger.info("  %s: %d", diag, count)

        return RecordBatch(
            schema_version="1",
            records=analyzed_records,
            stats={
                "analyzer_total": total,
                "diagnoses": counter_dict,
                "processed_at": datetime.now().isoformat(),
            },
            errors=[],
        )

    def _extract_failures_from_context(self, context) -> list[dict]:
        """Extract failures list from context config snapshot."""
        cfg = context.config_snapshot
        failures_data = cfg.get("failures_data", {})
        if isinstance(failures_data, dict):
            if "items" in failures_data:
                return failures_data["items"]
            if "failures" in failures_data:
                return failures_data["failures"]
            return [failures_data]
        return []

    def _diagnose_failure(self, failure: dict) -> Optional[str]:
        """Match failure to diagnosis pattern."""
        for diag_name, pattern in DIAGNOSIS_PATTERNS.items():
            if pattern["check"](failure):
                return diag_name
        return None

    def _suggest_fix(self, failure: dict, diagnosis: Optional[str]) -> str:
        """Get suggested fix for diagnosis."""
        if diagnosis and diagnosis in DIAGNOSIS_PATTERNS:
            return DIAGNOSIS_PATTERNS[diagnosis]["suggested_fix"]
        return "No automated fix available. Manual investigation required."

    def _assess_severity(self, failure: dict, diagnosis: Optional[str]) -> str:
        """Assess severity based on diagnosis or error type."""
        if diagnosis and diagnosis in DIAGNOSIS_PATTERNS:
            return DIAGNOSIS_PATTERNS[diagnosis]["severity"]

        # Fallback to error_type-based severity
        critical_errors = {"dns_error", "parse_error"}
        if failure.get("error_type") in critical_errors:
            return "high"
        return "low"

    def close(self) -> None:
        pass