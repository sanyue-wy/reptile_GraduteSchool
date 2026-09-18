"""Base plugin classes for V3.0 plugin architecture."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar


InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


@dataclass
class PluginMetadata:
    """Plugin metadata as declared in metadata.json."""
    name: str
    version: str
    author: str
    plugin_type: str  # spider, processor, storage, presenter, ui
    input_schema: str  # e.g., "TaskConfigDTO.v1"
    output_schema: str  # e.g., "RawDataBatch.v1"
    entry_point: str  # e.g., "plugins.spiders.static_html.plugin:StaticHtmlSpiderPlugin"
    dependencies: list[str] = field(default_factory=list)
    min_core_version: str = "3.0.0"
    config_schema: dict[str, Any] = field(default_factory=dict)
    license: str = "MIT"


class PluginContext:
    """Context injected into plugins during execution.

    Provides access to managed HTTP session, cache, progress tracking,
    storage, logging, allowed paths, cancellation token, and config snapshot.
    """
    def __init__(
        self,
        http: Any = None,  # PoliteSession
        cache: Any = None,
        progress: Any = None,
        storage: Any = None,
        logger: Any = None,
        allowed_paths: list[str] = None,
        cancel_token: Any = None,
        config_snapshot: dict[str, Any] = None,
        registry_revision: int = 0,
        task_id: str = "",
        run_id: str = "",
    ):
        self.http = http
        self.cache = cache
        self.progress = progress
        self.storage = storage
        self.logger = logger
        self.allowed_paths = allowed_paths or []
        self.cancel_token = cancel_token
        self.config_snapshot = config_snapshot or {}
        self.registry_revision = registry_revision
        self.task_id = task_id
        self.run_id = run_id

    def check_cancelled(self) -> bool:
        """Check if cancellation has been requested."""
        if self.cancel_token and hasattr(self.cancel_token, "is_set"):
            return self.cancel_token.is_set()
        return False


class BasePlugin(ABC, Generic[InputT, OutputT]):
    """Base class for all V3.0 plugins.

    Attributes:
        name: Unique plugin identifier (e.g., "static_html")
        version: Semantic version string (e.g., "1.0.0")
        plugin_type: One of "spider", "processor", "storage", "presenter", "ui"
        input_schema: JSON Schema ID for input validation (e.g., "TaskConfigDTO.v1")
        output_schema: JSON Schema ID for output validation (e.g., "RawDataBatch.v1")

    Methods:
        setup(context): Called once before execute(). Initialize resources here.
        execute(data, context): Main plugin logic. Must be implemented by subclasses.
        close(): Called after execute() for cleanup.
    """
    name: str = ""
    version: str = "1.0.0"
    plugin_type: str = ""
    input_schema: str = ""
    output_schema: str = ""

    def __init__(self):
        self._metadata: PluginMetadata | None = None

    @property
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata for registration."""
        if self._metadata is None:
            self._metadata = PluginMetadata(
                name=self.name,
                version=self.version,
                author="unknown",
                plugin_type=self.plugin_type,
                input_schema=self.input_schema,
                output_schema=self.output_schema,
                entry_point=self.__class__.__module__ + ":" + self.__class__.__name__,
            )
        return self._metadata

    def setup(self, context: PluginContext) -> None:
        """Initialize plugin resources. Called once before execute().

        Override to establish connections, load models, etc.
        """
        pass

    @abstractmethod
    def execute(self, data: InputT, context: PluginContext) -> OutputT:
        """Execute the plugin's main logic.

        Args:
            data: Input DTO validated against input_schema
            context: PluginContext with HTTP, cache, progress, etc.

        Returns:
            Output DTO validated against output_schema

        Raises:
            Exception: Any exception will be caught and wrapped in ErrorDTO
        """
        raise NotImplementedError

    def close(self) -> None:
        """Clean up resources. Called after execute() or on error."""
        pass


class PresenterPlugin(BasePlugin):
    """Specialized base class for presenter plugins.

    Presenters render RecordBatch data into human-readable formats.
    The execute() method is the single required entry point.

    Subclasses that prefer separate template rendering can override
    the render() hook, which is called by the default execute() implementation.
    """
    plugin_type = "presenter"

    def execute(self, data: Any, context: PluginContext) -> Any:
        """Execute presenter: render data to output format.

        Default implementation calls render() and wraps result in RenderedOutputDTO.
        Override entirely if you need custom logic.

        Args:
            data: PresentationRequest DTO
            context: PluginContext

        Returns:
            RenderedOutputDTO
        """
        from contracts.output import RenderedOutputDTO
        from uuid import uuid4
        from datetime import datetime

        rendered = self.render(data, context)

        if isinstance(rendered, RenderedOutputDTO):
            return rendered

        # If render() returns a path string, wrap it
        if isinstance(rendered, str):
            return RenderedOutputDTO(
                output_id=uuid4().hex,
                output_format=self.output_format,
                path=rendered,
            )

        raise TypeError(f"PresenterPlugin.render() must return RenderedOutputDTO or path string, got {type(rendered)}")

    def render(self, data: Any, context: PluginContext) -> Any:
        """Render hook for template-based presenters.

        Override this instead of execute() if you follow the standard
        pattern of: load template -> render with data -> write file.

        Args:
            data: PresentationRequest DTO
            context: PluginContext

        Returns:
            RenderedOutputDTO or output file path (str)
        """
        raise NotImplementedError

    @property
    def output_format(self) -> str:
        """Output format identifier (html, text, markdown, jsonl, csv, pdf)."""
        return self.name.replace("_presenter", "").replace("presenter_", "")


# Re-export for convenience
__all__ = [
    "PluginMetadata",
    "PluginContext",
    "BasePlugin",
    "PresenterPlugin",
]