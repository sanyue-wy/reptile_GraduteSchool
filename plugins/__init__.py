# -*- coding: utf-8 -*-
"""
V3.0 Plugin System

Plugin types:
- spider: Data acquisition (TaskConfigDTO → RawDataBatch)
- processor: Data processing (RawDataBatch → RecordBatch → RecordBatch)
- storage: Data persistence (StoreRequest → StoreReceipt)
- presenter: Output rendering (PresentationRequest → RenderedOutputDTO)
- ui: UI component (ViewModel → UIComponentDTO)
"""

from plugins.plugin_manifest import PluginManifestDTO
from plugins.base import (
    PluginMetadata,
    PluginContext,
    BasePlugin,
    PresenterPlugin,
    ParserPlugin,
    RecordProcessorPlugin,
    StoragePlugin,
    UIPlugin,
)

__all__ = [
    # DTOs
    "PluginManifestDTO",
    # Base classes
    "PluginMetadata",
    "PluginContext",
    "BasePlugin",
    "PresenterPlugin",
    "ParserPlugin",
    "RecordProcessorPlugin",
    "StoragePlugin",
    "UIPlugin",
]
