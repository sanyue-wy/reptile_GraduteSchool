# -*- coding: utf-8 -*-
"""
Plugin Manifest DTO for V3.0 plugin architecture.

This module defines the PluginManifestDTO class that represents the
canonical structure of plugin metadata from metadata.json files.
External developers can use this for plugin development validation.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PluginManifestDTO:
    """Canonical plugin manifest declared in metadata.json.

    This is the single source of truth for plugin identity, dependencies,
    and configuration schema. External developers SHOULD validate their
    plugins against this DTO before submission.

    Attributes:
        name: Unique plugin identifier (e.g., "static_html", "faculty_parser")
            Directory name MUST match this field.
        version: Semantic version string (e.g., "1.0.0", "2.1.3")
            Must follow semver: MAJOR.MINOR.PATCH
        author: Author/dMaintainer contact or team name
        plugin_type: One of "spider", "processor", "storage", "presenter", "ui"
        input_schema: JSON Schema ID for input validation (e.g., "TaskConfigDTO.v1")
        output_schema: JSON Schema ID for output validation (e.g., "RawDataBatch.v1")
        entry_point: Import path to plugin class, format: "module.path:ClassName"
            Directory name, module name, and class name SHOULD be consistent.
        dependencies: Required dependencies (pip package names)
        optional_dependencies: Optional dependencies (pip package names)
        min_core_version: Minimum reptile core version required (e.g., "3.0.0")
        config_schema: JSON Schema for plugin configuration parameters
        license: License identifier (e.g., "MIT", "GPL-3.0", "AGPL-3.0")
        description_long: Human-readable plugin description
        installed_at: ISO 8601 timestamp when installed (populated by system)
        updated_at: ISO 8601 timestamp when last updated (populated by system)

    Naming Conventions (§14.4):
        - 目录名 (Directory): plugins/{type}s/{name}/ (e.g., plugins/spiders/static_html/)
        - name 字段: 小写+下划线 (lowercase_with_underscores)
        - entry_point: plugins.{type}s.{name}.plugin:{Name}Plugin
          (e.g., plugins.spiders.static_html.plugin:StaticHtmlSpiderPlugin)
    """

    # Required fields
    name: str
    version: str
    author: str
    plugin_type: str  # spider, processor, storage, presenter, ui
    input_schema: str  # e.g., "TaskConfigDTO.v1"
    output_schema: str  # e.g., "RawDataBatch.v1"
    entry_point: str  # e.g., "plugins.spiders.static_html.plugin:StaticHtmlSpiderPlugin"

    # Optional fields with defaults
    dependencies: list[str] = field(default_factory=list)
    optional_dependencies: list[str] = field(default_factory=list)
    min_core_version: str = "3.0.0"
    config_schema: dict[str, Any] = field(default_factory=dict)
    license: str = "MIT"
    description_long: Optional[str] = None
    installed_at: Optional[str] = None
    updated_at: Optional[str] = None

    # JSON Schema for validation
    @classmethod
    def v1_schema(cls) -> dict:
        """Return JSON Schema for PluginManifestDTO v1."""
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
                "version": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$"},
                "author": {"type": "string", "minLength": 1},
                "plugin_type": {
                    "type": "string",
                    "enum": ["spider", "processor", "storage", "presenter", "ui"]
                },
                "input_schema": {"type": "string"},
                "output_schema": {"type": "string"},
                "entry_point": {"type": "string", "pattern": "^[a-zA-Z0-9_.]+:[A-Za-z][a-zA-Z0-9]*$"},
                "dependencies": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "optional_dependencies": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "min_core_version": {"type": "string"},
                "config_schema": {"type": "object"},
                "license": {"type": "string"},
                "description_long": {"type": ["string", "null"]},
                "installed_at": {"type": ["string", "null"], "format": "date-time"},
                "updated_at": {"type": ["string", "null"], "format": "date-time"}
            },
            "required": ["name", "version", "author", "plugin_type", "input_schema", "output_schema", "entry_point"],
            "additionalProperties": False
        }

    def __post_init__(self):
        """Validate required constraints after initialization."""
        # Validate name format
        import re
        if not re.match(r"^[a-z][a-z0-9_]*$", self.name):
            raise ValueError(f"Plugin name '{self.name}' must be lowercase_with_underscores format")

        # Validate version format
        if not re.match(r"^\d+\.\d+\.\d+$", self.version):
            raise ValueError(f"Version '{self.version}' must follow semver (MAJOR.MINOR.PATCH)")

        # Validate plugin_type
        valid_types = {"spider", "processor", "storage", "presenter", "ui"}
        if self.plugin_type not in valid_types:
            raise ValueError(f"plugin_type '{self.plugin_type}' must be one of {valid_types}")

        # Validate entry_point format
        if ":" not in self.entry_point:
            raise ValueError(f"entry_point '{self.entry_point}' must contain ':' separator")

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result = {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "plugin_type": self.plugin_type,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "entry_point": self.entry_point,
            "dependencies": self.dependencies,
            "optional_dependencies": self.optional_dependencies,
            "min_core_version": self.min_core_version,
            "config_schema": self.config_schema,
            "license": self.license,
        }
        if self.description_long is not None:
            result["description_long"] = self.description_long
        if self.installed_at is not None:
            result["installed_at"] = self.installed_at
        if self.updated_at is not None:
            result["updated_at"] = self.updated_at
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PluginManifestDTO":
        """Create from JSON dict, handling optional fields."""
        return cls(
            name=data["name"],
            version=data["version"],
            author=data["author"],
            plugin_type=data["plugin_type"],
            input_schema=data["input_schema"],
            output_schema=data["output_schema"],
            entry_point=data["entry_point"],
            dependencies=data.get("dependencies", []),
            optional_dependencies=data.get("optional_dependencies", []),
            min_core_version=data.get("min_core_version", "3.0.0"),
            config_schema=data.get("config_schema", {}),
            license=data.get("license", "MIT"),
            description_long=data.get("description_long"),
            installed_at=data.get("installed_at"),
            updated_at=data.get("updated_at"),
        )

    def validate(self) -> bool:
        """Validate against JSON Schema."""
        import jsonschema
        jsonschema.validate(self.to_dict(), self.v1_schema())
        return True

    @classmethod
    def validate_from_dict(cls, data: dict[str, Any]) -> bool:
        """Validate a dict against the schema without creating instance."""
        import jsonschema
        schema = cls.v1_schema()
        jsonschema.validate(data, schema)
        return True