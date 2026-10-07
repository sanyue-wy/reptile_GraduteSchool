# -*- coding: utf-8 -*-
"""
Domain Rewriter Processor Plugin
==================================
Rewrites subdomains based on domain_kb.json verified mappings.

Input:  TaskConfigDTO with target_url
Output: TaskConfigDTO with rewritten target_url
"""

import json
import logging
from pathlib import Path
from urllib.parse import urlparse

from contracts.task import TaskConfigDTO
from plugins.base import BasePlugin, PluginContext

from typing import Optional

logger = logging.getLogger(__name__)

_DOMAIN_KB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "domain_kb.json"


class DomainRewriterProcessor(BasePlugin):
    """Rewrite subdomains based on verified domain mappings.

    If a subdomain is in the verified list, use it directly.
    If not verified but exists in subdomains, use main domain as fallback.
    """

    name = "domain_rewriter"
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

        if not hostname:
            return data

        # Extract school from URL or config
        school_name = self._extract_school_name(data)
        if not school_name or school_name not in self._domain_kb.get("mappings", {}):
            logger.debug("No mapping found for school from URL: %s", hostname)
            return data

        mapping = self._domain_kb["mappings"][school_name]
        main_domain = mapping.get("main", "")
        verified = mapping.get("verified", {}).get("szdw", [])
        subdomains = mapping.get("subdomains", {}).get("szdw", [])

        # Extract current subdomain
        parts = hostname.split(".")
        current_sub = parts[0] if len(parts) > 2 else ""

        domain_corrected = False

        if current_sub:
            # Check if current subdomain is verified
            if hostname in verified or f"{current_sub}.{main_domain}" in verified:
                domain_corrected = True
                new_hostname = hostname
            elif current_sub in subdomains:
                if current_sub in verified:
                    new_hostname = f"{current_sub}.{main_domain}"
                    domain_corrected = True
                else:
                    # Not verified, fall back to main domain
                    new_hostname = main_domain
                    domain_corrected = True
                    logger.info("Subdomain %s not verified, falling back to %s", current_sub, main_domain)
            elif main_domain:
                new_hostname = f"www.{main_domain}" if main_domain else hostname
                domain_corrected = True
                logger.info("No matching subdomain for %s, using %s", hostname, new_hostname)
            else:
                return data
        else:
            # Use main domain or www
            if main_domain:
                new_hostname = f"www.{main_domain}" if hostname != main_domain else hostname
                domain_corrected = True
            else:
                return data

        if domain_corrected:
            new_url = target_url.replace(hostname, new_hostname, 1)
            logger.info("Domain rewrite: %s -> %s", hostname, new_hostname)

            object.__setattr__(data, 'target_url', new_url)

            if not hasattr(data, 'metadata'):
                object.__setattr__(data, 'metadata', {})
            if hasattr(data, 'metadata') and isinstance(data.metadata, dict):
                data.metadata["url_rewrite"] = True
                data.metadata["rewritten_hostname"] = new_hostname

        return data

    def _extract_school_name(self, data: TaskConfigDTO) -> Optional[str]:
        """Extract school name from TaskConfigDTO."""
        if hasattr(data, 'school') and data.school:
            return data.school
        if data.config_snapshot.get('school'):
            return data.config_snapshot['school']
        # Also check university field (used in school_data.json)
        uni = data.config_snapshot.get('university')
        if uni and uni in self._domain_kb.get("mappings", {}):
            return uni
        # Fuzzy match: check if any domain_kb key is contained in the university field
        if uni:
            for school_name in self._domain_kb.get("mappings", {}).keys():
                if school_name in uni or uni in school_name:
                    return school_name
        return None
