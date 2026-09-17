"""Shared export and processor orchestration; pipeline return values are preserved."""
from copy import deepcopy
from config.plugins import is_enabled, load_plugin_config, plugin_config
from exporters import dispatch as dispatch_exporter
from processors import dispatch as dispatch_processor
from pipelines.export import export_merged, export_summary, export_failures


class ExportService:
    export_merged = staticmethod(export_merged)
    export_summary = staticmethod(export_summary)
    export_failures = staticmethod(export_failures)

    def run_processor_pipeline(self, records, ctx=None, *, load_config=None, enabled=None,
                               config_for=None, dispatch=None):
        load_config = load_config or load_plugin_config
        enabled = enabled or is_enabled
        config_for = config_for or plugin_config
        dispatch = dispatch or dispatch_processor
        context = dict(ctx or {})
        records = deepcopy(records)
        pipeline = load_config().get("pipeline", {}).get("processors", {})
        enabled_pairs = [(int(weight), name) for name, weight in pipeline.items()
                         if enabled("processor", name)]
        for _, name in sorted(enabled_pairs):
            records = dispatch(name, records, {
                **context, "plugin_config": config_for("processor", name)})
        return records

    def run_export_pipeline(self, records, output_dir, *, load_config=None, enabled=None,
                            dispatch=None):
        load_config = load_config or load_plugin_config
        enabled = enabled or is_enabled
        dispatch = dispatch or dispatch_exporter
        pipeline = load_config().get("pipeline", {}).get("exporters", {})
        enabled_pairs = [(int(weight), name) for name, weight in pipeline.items()
                         if enabled("exporter", name)]
        return {name: dispatch(name, records, output_dir) for _, name in sorted(enabled_pairs)}
