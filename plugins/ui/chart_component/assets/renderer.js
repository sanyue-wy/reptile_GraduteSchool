/**
 * Chart.js Renderer for ChartComponentPlugin
 * ===========================================
 *
 * Frontend renderer for declarative chart components (bar, line, pie).
 * Uses Chart.js v4.4.3 via UMD bundle.
 *
 * Exports:
 *   - renderChart(container, component, data) -> Chart instance
 *   - updateChart(chart, component, data) -> void
 *   - destroyChart(chart) -> void
 *
 * Component payload schema:
 *   {
 *     chart_type: "bar" | "line" | "pie",
 *     x_field: string,
 *     y_field: string,
 *     group_by?: string | null
 *   }
 */

(function (global) {
  'use strict';

  // Chart.js namespace (loaded via UMD)
  const Chart = global.Chart;

  if (!Chart) {
    console.error('[ChartRenderer] Chart.js not loaded. Ensure chart.js@4.4.3 is included before this script.');
    return;
  }

  // Default color palette (brand-neutral, accessible)
  const DEFAULT_COLORS = [
    '#4C78A8', '#F58518', '#E45756', '#72B7B2', '#54A24B',
    '#EECA3B', '#B279A2', '#FF9DA7', '#9D755D', '#BAB0AC'
  ];

  const DEFAULT_BACKGROUND_COLORS = [
    'rgba(76, 120, 168, 0.7)',   // #4C78A8
    'rgba(245, 133, 24, 0.7)',   // #F58518
    'rgba(228, 87, 86, 0.7)',    // #E45756
    'rgba(114, 183, 178, 0.7)',  // #72B7B2
    'rgba(84, 162, 75, 0.7)',    // #54A24B
    'rgba(238, 202, 59, 0.7)',   // #EECA3B
    'rgba(178, 121, 162, 0.7)',  // #B279A2
    'rgba(255, 157, 167, 0.7)',  // #FF9DA7
    'rgba(157, 117, 93, 0.7)',   // #9D755D
    'rgba(186, 176, 172, 0.7)'   // #BAB0AC
  ];

  /**
   * Generate dataset configuration from data and payload
   */
  function buildDatasets(data, payload, chartType) {
    const { x_field, y_field, group_by } = payload;
    const datasets = [];

    if (!data || !data.length) {
      return datasets;
    }

    // Group data if group_by is specified
    const groups = group_by
      ? groupDataBy(data, group_by)
      : { default: data };

    let colorIndex = 0;
    for (const [groupName, groupData] of Object.entries(groups)) {
      const labels = groupData.map(row => row[x_field]);
      const values = groupData.map(row => row[y_field]);

      const borderColor = DEFAULT_COLORS[colorIndex % DEFAULT_COLORS.length];
      const backgroundColor = DEFAULT_BACKGROUND_COLORS[colorIndex % DEFAULT_BACKGROUND_COLORS.length];

      const dataset = {
        label: groupName === 'default' ? y_field : groupName,
        data: values,
        borderColor: borderColor,
        backgroundColor: chartType === 'pie' || chartType === 'doughnut'
          ? DEFAULT_COLORS.slice(0, values.length).map((c, i) => DEFAULT_BACKGROUND_COLORS[i])
          : backgroundColor,
        borderWidth: 2,
        tension: chartType === 'line' ? 0.3 : 0,
        fill: chartType === 'line' ? false : true
      };

      datasets.push(dataset);
      colorIndex++;
    }

    return datasets;
  }

  /**
   * Group array of objects by field value
   */
  function groupDataBy(data, field) {
    return data.reduce((acc, row) => {
      const key = row[field] ?? 'unknown';
      if (!acc[key]) acc[key] = [];
      acc[key].push(row);
      return acc;
    }, {});
  }

  /**
   * Get chart type config for Chart.js
   */
  function getChartJsType(chartType) {
    const map = {
      'bar': 'bar',
      'line': 'line',
      'pie': 'pie'
    };
    return map[chartType] || 'bar';
  }

  /**
   * Build chart options based on type and payload
   */
  function buildOptions(payload, chartType) {
    const isPie = chartType === 'pie';
    const { x_field, y_field } = payload;

    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false
      },
      plugins: {
        legend: {
          display: !isPie || (payload.group_by && payload.group_by !== 'default'),
          position: 'top',
          labels: {
            usePointStyle: true,
            padding: 16,
            font: { size: 12 }
          }
        },
        tooltip: {
          enabled: true,
          mode: isPie ? 'nearest' : 'index',
          intersect: false,
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
          titleFont: { size: 13 },
          bodyFont: { size: 12 },
          padding: 12,
          callbacks: {
            label: function (context) {
              const label = context.dataset.label || '';
              const value = context.parsed.y ?? context.parsed;
              return `${label}: ${formatValue(value)}`;
            }
          }
        },
        title: {
          display: false
        }
      },
      scales: isPie ? {} : {
        x: {
          title: {
            display: true,
            text: x_field,
            font: { size: 12, weight: 'bold' }
          },
          ticks: {
            maxRotation: 45,
            minRotation: 0,
            autoSkip: true,
            maxTicksLimit: 20,
            font: { size: 11 }
          },
          grid: {
            display: false
          }
        },
        y: {
          title: {
            display: true,
            text: y_field,
            font: { size: 12, weight: 'bold' }
          },
          beginAtZero: true,
          ticks: {
            font: { size: 11 },
            callback: function (value) {
              return formatValue(value);
            }
          },
          grid: {
            color: 'rgba(0, 0, 0, 0.05)'
          }
        }
      },
      animation: {
        duration: 750,
        easing: 'easeOutQuart'
      }
    };
  }

  /**
   * Format numeric value for display
   */
  function formatValue(value) {
    if (typeof value !== 'number') return String(value);
    if (value >= 1e9) return (value / 1e9).toFixed(1) + 'B';
    if (value >= 1e6) return (value / 1e6).toFixed(1) + 'M';
    if (value >= 1e3) return (value / 1e3).toFixed(1) + 'K';
    if (value % 1 !== 0) return value.toFixed(2);
    return value.toLocaleString();
  }

  /**
   * Render a chart component
   *
   * @param {HTMLElement} container - Canvas container element
   * @param {Object} component - UIComponentDTO with chart payload
   * @param {Array} data - Array of data objects
   * @returns {Chart} Chart.js instance
   */
  function renderChart(container, component, data) {
    const payload = component.payload || {};
    const chartType = getChartJsType(payload.chart_type || 'bar');

    // Ensure container has a canvas
    let canvas = container.querySelector('canvas');
    if (!canvas) {
      canvas = document.createElement('canvas');
      container.innerHTML = '';
      container.appendChild(canvas);
    }

    // Set canvas size
    const rect = container.getBoundingClientRect();
    canvas.width = rect.width * (window.devicePixelRatio || 1);
    canvas.height = rect.height * (window.devicePixelRatio || 1);
    canvas.style.width = '100%';
    canvas.style.height = '100%';

    const ctx = canvas.getContext('2d');
    if (!ctx) {
      throw new Error('Failed to get 2D context from canvas');
    }

    // Scale context for high DPI
    const dpr = window.devicePixelRatio || 1;
    ctx.scale(dpr, dpr);

    // Build datasets
    const datasets = buildDatasets(data, payload, chartType);

    // Get labels from first dataset (or first data row)
    const labels = data.length > 0
      ? data.map(row => row[payload.x_field])
      : [];

    // Create chart
    const chart = new Chart(ctx, {
      type: chartType,
      data: {
        labels: labels,
        datasets: datasets
      },
      options: buildOptions(payload, chartType)
    });

    // Store component reference for updates
    chart.__component = component;
    chart.__payload = payload;

    // Emit render event
    container.dispatchEvent(new CustomEvent('chart:render', {
      detail: { chart, component },
      bubbles: true
    }));

    return chart;
  }

  /**
   * Update an existing chart with new data
   *
   * @param {Chart} chart - Existing Chart.js instance
   * @param {Object} component - Updated UIComponentDTO
   * @param {Array} data - New data array
   */
  function updateChart(chart, component, data) {
    if (!chart || !chart.data) return;

    const payload = component.payload || chart.__payload;
    const chartType = getChartJsType(payload.chart_type || 'bar');

    // Rebuild datasets
    const datasets = buildDatasets(data, payload, chartType);
    const labels = data.length > 0
      ? data.map(row => row[payload.x_field])
      : [];

    // Update chart data
    chart.data.labels = labels;
    chart.data.datasets = datasets;

    // Update options if chart type changed
    if (chart.config.type !== chartType) {
      chart.config.type = chartType;
      chart.options = buildOptions(payload, chartType);
    }

    chart.update('active');

    // Emit update event
    const container = chart.canvas.parentElement;
    if (container) {
      container.dispatchEvent(new CustomEvent('chart:update', {
        detail: { chart, component },
        bubbles: true
      }));
    }
  }

  /**
   * Destroy a chart instance
   *
   * @param {Chart} chart - Chart.js instance to destroy
   */
  function destroyChart(chart) {
    if (chart && typeof chart.destroy === 'function') {
      const container = chart.canvas.parentElement;
      chart.destroy();

      if (container) {
        container.dispatchEvent(new CustomEvent('chart:destroy', {
          detail: { chart },
          bubbles: true
        }));
      }
    }
  }

  /**
   * Register chart component with data source
   * Called by the UI framework when component mounts
   *
   * @param {HTMLElement} container - Container element
   * @param {Object} component - UIComponentDTO
   * @param {Function} fetchData - Async function returning data array
   */
  async function mountChart(container, component, fetchData) {
    try {
      const data = await fetchData();
      const chart = renderChart(container, component, data);

      // Store chart instance on container for later access
      container.__chartInstance = chart;

      return chart;
    } catch (error) {
      console.error('[ChartRenderer] Failed to mount chart:', error);
      container.innerHTML = `<div class="chart-error">Failed to render chart: ${error.message}</div>`;
      throw error;
    }
  }

  /**
   * Unmount chart component
   * Called by the UI framework when component unmounts
   *
   * @param {HTMLElement} container - Container element
   */
  function unmountChart(container) {
    const chart = container.__chartInstance;
    if (chart) {
      destroyChart(chart);
      container.__chartInstance = null;
    }
  }

  // Export public API
  global.ChartRenderer = {
    render: renderChart,
    update: updateChart,
    destroy: destroyChart,
    mount: mountChart,
    unmount: unmountChart,
    version: '1.0.0',
    chartJsVersion: Chart.version
  };

  // Also support named exports for module systems
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = global.ChartRenderer;
  }

  // AMD support
  if (typeof define === 'function' && define.amd) {
    define('ChartRenderer', [], function () { return global.ChartRenderer; });
  }

})(typeof window !== 'undefined' ? window : typeof global !== 'undefined' ? global : this);