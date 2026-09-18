"""Card Component UI Plugin.

Renders data as interactive cards with configurable fields, images, and links.
Uses a plain JavaScript template renderer for client-side rendering.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from contracts.ui import UIComponentDTO, ViewModel, validate_ui_component
from plugins.base import BasePlugin, PluginContext

logger = logging.getLogger(__name__)


@dataclass
class CardComponentPayload:
    """Payload schema for card component configuration.

    Attributes:
        card_fields: List of field names to display on each card.
            Fields are rendered in the order specified.
        image_field: Optional field name containing image URL for card thumbnail.
        link_field: Optional field name containing URL for card click-through link.
        title_field: Optional field name to use as card title (defaults to first card_field).
        subtitle_field: Optional field name to use as card subtitle.
        max_cards: Maximum number of cards to render per page (default: 20).
        card_layout: Layout style - "horizontal", "vertical", or "grid" (default: "grid").
        show_border: Whether to show card borders (default: true).
        hover_effect: Whether to enable hover elevation effect (default: true).
    """
    card_fields: list[str] = field(default_factory=list)
    image_field: str = ""
    link_field: str = ""
    title_field: str = ""
    subtitle_field: str = ""
    max_cards: int = 20
    card_layout: str = "grid"
    show_border: bool = True
    hover_effect: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "card_fields": self.card_fields,
            "image_field": self.image_field,
            "link_field": self.link_field,
            "title_field": self.title_field,
            "subtitle_field": self.subtitle_field,
            "max_cards": self.max_cards,
            "card_layout": self.card_layout,
            "show_border": self.show_border,
            "hover_effect": self.hover_effect,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CardComponentPayload":
        """Create from dict, using defaults for missing fields."""
        return cls(
            card_fields=data.get("card_fields", []),
            image_field=data.get("image_field", ""),
            link_field=data.get("link_field", ""),
            title_field=data.get("title_field", ""),
            subtitle_field=data.get("subtitle_field", ""),
            max_cards=data.get("max_cards", 20),
            card_layout=data.get("card_layout", "grid"),
            show_border=data.get("show_border", True),
            hover_effect=data.get("hover_effect", True),
        )


# JSON Schema for payload validation
CARD_COMPONENT_PAYLOAD_SCHEMA = {
    "type": "object",
    "properties": {
        "card_fields": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "minItems": 1,
            "description": "List of field names to display on each card",
        },
        "image_field": {
            "type": "string",
            "description": "Field name containing image URL for card thumbnail",
        },
        "link_field": {
            "type": "string",
            "description": "Field name containing URL for card click-through link",
        },
        "title_field": {
            "type": "string",
            "description": "Field name to use as card title",
        },
        "subtitle_field": {
            "type": "string",
            "description": "Field name to use as card subtitle",
        },
        "max_cards": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "default": 20,
            "description": "Maximum number of cards to render per page",
        },
        "card_layout": {
            "type": "string",
            "enum": ["horizontal", "vertical", "grid"],
            "default": "grid",
            "description": "Layout style for cards",
        },
        "show_border": {
            "type": "boolean",
            "default": True,
            "description": "Whether to show card borders",
        },
        "hover_effect": {
            "type": "boolean",
            "default": True,
            "description": "Whether to enable hover elevation effect",
        },
    },
    "required": ["card_fields"],
    "additionalProperties": False,
}


# Renderer manifest for plain JS template renderer
CARD_RENDERER_MANIFEST = {
    "renderer_id": "plain_js_template",
    "version": "1.0.0",
    "component_type": "card",
    "entry_point": "render_card_component",
    "description": "Plain JavaScript template renderer for card components",
    "dependencies": [],
    "api_version": "1",
    "template": """
(function() {
  'use strict';

  /**
   * Plain JS Template Renderer for Card Components
   * Renders card components without any framework dependencies
   */

  // Component registry
  const renderers = {};

  /**
   * Register a renderer function
   * @param {string} id - Renderer identifier
   * @param {Function} fn - Renderer function
   */
  function registerRenderer(id, fn) {
    renderers[id] = fn;
  }

  /**
   * Get registered renderer
   * @param {string} id - Renderer identifier
   * @returns {Function|null} Renderer function or null if not found
   */
  function getRenderer(id) {
    return renderers[id] || null;
  }

  /**
   * Escape HTML to prevent XSS
   * @param {string} str - String to escape
   * @returns {string} Escaped string
   */
  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&')
      .replace(/</g, '<')
      .replace(/>/g, '>')
      .replace(/"/g, '"')
      .replace(/'/g, '&#039;');
  }

  /**
   * Format value based on field description
   * @param {any} value - Value to format
   * @param {Object} fieldDesc - Field description from ViewModel
   * @returns {string} Formatted value
   */
  function formatValue(value, fieldDesc) {
    if (value === null || value === undefined || value === '') {
      return '<span class="card-empty">—</span>';
    }

    if (!fieldDesc) {
      return escapeHtml(String(value));
    }

    const { type, format } = fieldDesc;

    switch (type) {
      case 'number':
        if (format === 'currency') {
          return '¥' + Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2 });
        }
        if (format === 'percent') {
          return (Number(value) * 100).toFixed(1) + '%';
        }
        return Number(value).toLocaleString('zh-CN');

      case 'date':
      case 'datetime':
        try {
          const date = new Date(value);
          if (format === 'relative') {
            const diff = Date.now() - date.getTime();
            const days = Math.floor(diff / (1000 * 60 * 60 * 24));
            if (days === 0) return '今天';
            if (days === 1) return '昨天';
            if (days < 7) return days + '天前';
            if (days < 30) return Math.floor(days / 7) + '周前';
            return Math.floor(days / 30) + '月前';
          }
          return date.toLocaleDateString('zh-CN', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
          });
        } catch {
          return escapeHtml(String(value));
        }

      case 'boolean':
        return value ? '<span class="card-bool-true">是</span>' : '<span class="card-bool-false">否</span>';

      case 'url':
        return '<a href="' + escapeHtml(String(value)) + '" target="_blank" rel="noopener">' + escapeHtml(String(value)) + '</a>';

      default:
        return escapeHtml(String(value));
    }
  }

  /**
   * Render a single card
   * @param {Object} record - Data record
   * @param {CardComponentPayload} payload - Component payload config
   * @param {Object} fieldDescriptions - Field descriptions from ViewModel
   * @returns {string} HTML string for the card
   */
  function renderCard(record, payload, fieldDescriptions) {
    const {
      card_fields,
      image_field,
      link_field,
      title_field,
      subtitle_field,
      card_layout,
      show_border,
      hover_effect,
    } = payload;

    // Determine title and subtitle
    const titleKey = title_field || card_fields[0];
    const subtitleKey = subtitle_field || (card_fields[1] || '');

    const title = record[titleKey] ?? '';
    const subtitle = subtitleKey ? (record[subtitleKey] ?? '') : '';
    const imageUrl = image_field ? (record[image_field] ?? '') : '';
    const linkUrl = link_field ? (record[link_field] ?? '') : '';

    // Build card classes
    const classes = ['card-component'];
    if (card_layout !== 'grid') classes.push('card-' + card_layout);
    if (!show_border) classes.push('card-no-border');
    if (hover_effect) classes.push('card-hover');

    // Build fields HTML
    let fieldsHtml = '';
    card_fields.forEach(function(fieldName) {
      // Skip title and subtitle if they're already rendered separately
      if (fieldName === titleKey || fieldName === subtitleKey) return;
      // Skip image and link fields (handled separately)
      if (fieldName === image_field || fieldName === link_field) return;

      const value = record[fieldName];
      const fieldDesc = fieldDescriptions[fieldName] || {};
      const formatted = formatValue(value, fieldDesc);
      const label = fieldDesc.label || fieldName;

      fieldsHtml += '<div class="card-field">';
      fieldsHtml += '  <span class="card-field-label">' + escapeHtml(label) + ':</span>';
      fieldsHtml += '  <span class="card-field-value">' + formatted + '</span>';
      fieldsHtml += '</div>';
    });

    // Build image HTML
    let imageHtml = '';
    if (imageUrl) {
      imageHtml = '<div class="card-image">';
      imageHtml += '  <img src="' + escapeHtml(imageUrl) + '" alt="' + escapeHtml(title) + '" loading="lazy">';
      imageHtml += '</div>';
    }

    // Build link wrapper
    const cardContent = imageHtml +
      '<div class="card-body">' +
        '<h3 class="card-title">' + escapeHtml(title) + '</h3>' +
        (subtitle ? '<p class="card-subtitle">' + escapeHtml(subtitle) + '</p>' : '') +
        '<div class="card-fields">' + fieldsHtml + '</div>' +
      '</div>';

    if (linkUrl) {
      return '<a href="' + escapeHtml(linkUrl) + '" class="' + classes.join(' ') + '" target="_blank" rel="noopener">' + cardContent + '</a>';
    } else {
      return '<div class="' + classes.join(' ') + '">' + cardContent + '</div>';
    }
  }

  /**
   * Main render function for card component
   * @param {Object} params - Render parameters
   * @param {ViewModel} params.viewModel - ViewModel containing data and metadata
   * @param {CardComponentPayload} params.payload - Component payload configuration
   * @param {HTMLElement} params.container - Container element to render into
   * @returns {Promise<void>}
   */
  async function renderCardComponent(params) {
    const { viewModel, payload, container } = params;

    // Validate inputs
    if (!viewModel || !payload || !container) {
      throw new Error('Missing required parameters: viewModel, payload, container');
    }

    // Parse payload
    const cardPayload = CardComponentPayload.fromDict
      ? CardComponentPayload.fromDict(payload)
      : {
          card_fields: payload.card_fields || [],
          image_field: payload.image_field || '',
          link_field: payload.link_field || '',
          title_field: payload.title_field || '',
          subtitle_field: payload.subtitle_field || '',
          max_cards: payload.max_cards || 20,
          card_layout: payload.card_layout || 'grid',
          show_border: payload.show_border !== false,
          hover_effect: payload.hover_effect !== false,
        };

    // Get records from viewModel (simplified - assumes records are embedded or fetched)
    const records = viewModel.records || [];

    // Limit to max_cards
    const displayRecords = records.slice(0, cardPayload.max_cards);

    // Get field descriptions
    const fieldDescriptions = viewModel.field_descriptions || {};

    // Render cards
    let cardsHtml = '';
    displayRecords.forEach(function(record) {
      cardsHtml += renderCard(record, cardPayload, fieldDescriptions);
    });

    // Build container HTML
    const containerClasses = ['card-container', 'card-layout-' + cardPayload.card_layout];
    container.className = containerClasses.join(' ');
    container.innerHTML = cardsHtml;

    // Add styles if not already present
    if (!document.getElementById('card-component-styles')) {
      const style = document.createElement('style');
      style.id = 'card-component-styles';
      style.textContent = getCardStyles();
      document.head.appendChild(style);
    }
  }

  /**
   * Get CSS styles for card component
   * @returns {string} CSS stylesheet text
   */
  function getCardStyles() {
    return `
/* Card Component Styles */
.card-container {
  display: grid;
  gap: 16px;
  padding: 16px;
}

.card-container.card-layout-grid {
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
}

.card-container.card-layout-horizontal {
  grid-template-columns: 1fr;
}

.card-container.card-layout-vertical {
  grid-template-columns: 1fr;
}

.card-component {
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  text-decoration: none;
  color: inherit;
}

.card-component.card-no-border {
  box-shadow: none;
  border: 1px solid #e8e8e8;
}

.card-component.card-hover:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.card-component.card-horizontal {
  flex-direction: row;
  align-items: flex-start;
}

.card-component.card-vertical {
  flex-direction: column;
}

.card-image {
  width: 100%;
  height: 160px;
  overflow: hidden;
  border-radius: 8px 8px 0 0;
}

.card-horizontal .card-image {
  width: 200px;
  height: 100%;
  min-height: 160px;
  border-radius: 8px 0 0 8px;
}

.card-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s ease;
}

.card-component:hover .card-image img {
  transform: scale(1.05);
}

.card-body {
  padding: 16px;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.card-horizontal .card-body {
  padding: 16px;
}

.card-title {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: #1a1a1a;
  line-height: 1.4;
}

.card-subtitle {
  margin: 0 0 12px;
  font-size: 14px;
  color: #666;
  line-height: 1.4;
}

.card-fields {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: auto;
}

.card-field {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 13px;
}

.card-field-label {
  color: #999;
  font-weight: 500;
  min-width: 80px;
  flex-shrink: 0;
}

.card-field-value {
  color: #333;
  word-break: break-word;
}

.card-empty {
  color: #ccc;
  font-style: italic;
}

.card-bool-true {
  color: #52c41a;
  font-weight: 500;
}

.card-bool-false {
  color: #ff4d4f;
  font-weight: 500;
}

/* Responsive adjustments */
@media (max-width: 640px) {
  .card-container.card-layout-grid {
    grid-template-columns: 1fr;
  }

  .card-horizontal {
    flex-direction: column;
  }

  .card-horizontal .card-image {
    width: 100%;
    height: 160px;
    border-radius: 8px 8px 0 0;
  }
}

/* Dark mode support */
@media (prefers-color-scheme: dark) {
  .card-component {
    background: #1f1f1f;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  }

  .card-component.card-no-border {
    border-color: #434343;
  }

  .card-title {
    color: #e8e8e8;
  }

  .card-subtitle {
    color: #aaa;
  }

  .card-field-label {
    color: #888;
  }

  .card-field-value {
    color: #ddd;
  }
}
`;
  }

  // Export for module systems
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      registerRenderer,
      getRenderer,
      renderCardComponent,
      renderCard,
      formatValue,
      escapeHtml,
      CardComponentPayload,
    };
  } else {
    // Global registration for browser
    window.CardComponentRenderer = {
      registerRenderer,
      getRenderer,
      renderCardComponent,
      renderCard,
      formatValue,
      escapeHtml,
      CardComponentPayload: {
        fromDict: function(data) {
          return {
            card_fields: data.card_fields || [],
            image_field: data.image_field || '',
            link_field: data.link_field || '',
            title_field: data.title_field || '',
            subtitle_field: data.subtitle_field || '',
            max_cards: data.max_cards || 20,
            card_layout: data.card_layout || 'grid',
            show_border: data.show_border !== false,
            hover_effect: data.hover_effect !== false,
          };
        },
      },
    };
  }

  // Auto-register this renderer
  registerRenderer('plain_js_template', renderCardComponent);
})();
""",
}


class CardComponentPlugin(BasePlugin[ViewModel, UIComponentDTO]):
    """UI Plugin for rendering card components.

    Takes a ViewModel and produces a UIComponentDTO configured for card rendering
    with a plain JavaScript template renderer.

    Configuration (via params in plugin instance config):
        card_fields (list[str]): Required. Field names to display on each card.
        image_field (str): Optional. Field name containing image URL.
        link_field (str): Optional. Field name containing link URL.
        title_field (str): Optional. Field name for card title.
        subtitle_field (str): Optional. Field name for card subtitle.
        max_cards (int): Optional. Max cards per page (default: 20).
        card_layout (str): Optional. "horizontal" | "vertical" | "grid" (default: "grid").
        show_border (bool): Optional. Show card borders (default: true).
        hover_effect (bool): Optional. Enable hover effect (default: true).
    """

    name = "card_component"
    version = "1.0.0"
    plugin_type = "ui"
    input_schema = "ViewModel.v1"
    output_schema = "UIComponentDTO.v1"

    def __init__(self):
        super().__init__()
        self._renderer_manifest = CARD_RENDERER_MANIFEST

    def setup(self, context: PluginContext) -> None:
        """Initialize plugin with context."""
        self._context = context
        # Read plugin-specific config from context
        plugin_config = context.config_snapshot.get("plugins", {}).get("card_component", {})
        self._config = plugin_config
        logger.info("CardComponentPlugin setup complete")

    def execute(self, data: ViewModel, context: PluginContext) -> UIComponentDTO:
        """Execute card component rendering.

        Args:
            data: ViewModel containing dataset, records, and field descriptions
            context: PluginContext with runtime resources

        Returns:
            UIComponentDTO configured for card rendering
        """
        try:
            # Validate input
            if not isinstance(data, ViewModel):
                raise TypeError(f"Expected ViewModel, got {type(data).__name__}")

            # Build payload from config and data
            payload = self._build_payload(data)

            # Validate payload against schema
            self._validate_payload(payload)

            # Generate component ID
            component_id = f"card_{data.dataset}_{uuid4().hex[:8]}"

            # Create UIComponentDTO
            component = UIComponentDTO(
                component_id=component_id,
                component_type="card",
                renderer_id="plain_js_template",
                payload=payload.to_dict(),
                data_ref=data.data_ref or f"/api/data/{data.dataset}",
                events=[
                    {
                        "event": "click",
                        "handler": "navigateToDetail",
                        "description": "Navigate to detail page when card is clicked",
                    },
                    {
                        "event": "hover",
                        "handler": "showTooltip",
                        "description": "Show tooltip on card hover",
                    },
                ],
            )

            # Validate output
            validate_ui_component(component)

            logger.info(
                "Card component created: %s with %d fields",
                component_id,
                len(payload.card_fields),
            )

            return component

        except Exception as e:
            logger.exception("Card component generation failed")
            raise

    def _build_payload(self, view_model: ViewModel) -> CardComponentPayload:
        """Build card component payload from config and ViewModel.

        Priority: plugin config > ViewModel field_descriptions > defaults
        """
        config = getattr(self, "_config", {})

        # Get card_fields from config, or infer from ViewModel field_descriptions
        card_fields = config.get("card_fields")
        if not card_fields:
            # Use all fields from field_descriptions that have labels
            card_fields = [
                fname for fname, fdesc in view_model.field_descriptions.items()
                if isinstance(fdesc, dict) and fdesc.get("label")
            ]
            # Fallback: use first 5 fields
            if not card_fields and view_model.field_descriptions:
                card_fields = list(view_model.field_descriptions.keys())[:5]

        # Get optional fields from config with defaults
        image_field = config.get("image_field", "")
        link_field = config.get("link_field", "")
        title_field = config.get("title_field", "")
        subtitle_field = config.get("subtitle_field", "")
        max_cards = config.get("max_cards", 20)
        card_layout = config.get("card_layout", "grid")
        show_border = config.get("show_border", True)
        hover_effect = config.get("hover_effect", True)

        # If title_field not set, use first card_field
        if not title_field and card_fields:
            title_field = card_fields[0]

        # If subtitle_field not set, use second card_field
        if not subtitle_field and len(card_fields) > 1:
            subtitle_field = card_fields[1]

        return CardComponentPayload(
            card_fields=card_fields,
            image_field=image_field,
            link_field=link_field,
            title_field=title_field,
            subtitle_field=subtitle_field,
            max_cards=max_cards,
            card_layout=card_layout,
            show_border=show_border,
            hover_effect=hover_effect,
        )

    def _validate_payload(self, payload: CardComponentPayload) -> None:
        """Validate payload against JSON schema."""
        import jsonschema
        jsonschema.validate(payload.to_dict(), CARD_COMPONENT_PAYLOAD_SCHEMA)

    @property
    def renderer_manifest(self) -> dict[str, Any]:
        """Return the renderer manifest for this component."""
        return self._renderer_manifest

    def close(self) -> None:
        """Cleanup resources."""
        pass


# For backward compatibility and direct imports
__all__ = [
    "CardComponentPlugin",
    "CardComponentPayload",
    "CARD_COMPONENT_PAYLOAD_SCHEMA",
    "CARD_RENDERER_MANIFEST",
]