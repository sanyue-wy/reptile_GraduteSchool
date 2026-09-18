"""ThemeSwitcher - Pure frontend JavaScript for cycling themes in standalone HTML.

Embedded directly into the HTML output. No network requests.
Cycles through light/dark/custom themes by toggling CSS custom properties.
"""

THEME_SWITCHER_JS = """
(function() {
    'use strict';

    var THEMES = {
        'light': {
            '--color-primary': '#2c3e50',
            '--color-secondary': '#3498db',
            '--bg-primary': '#ffffff',
            '--bg-secondary': '#f8f9fa',
            '--text-primary': '#333333',
            '--text-secondary': '#666666',
            '--border-color': '#dee2e6'
        },
        'dark': {
            '--color-primary': '#ecf0f1',
            '--color-secondary': '#3498db',
            '--bg-primary': '#1a1a2e',
            '--bg-secondary': '#16213e',
            '--text-primary': '#e0e0e0',
            '--text-secondary': '#a0a0a0',
            '--border-color': '#333355'
        },
        'sepia': {
            '--color-primary': '#5b4636',
            '--color-secondary': '#8b6914',
            '--bg-primary': '#f4ecd8',
            '--bg-secondary': '#efe6d0',
            '--text-primary': '#3e2c1c',
            '--text-secondary': '#7a6a5a',
            '--border-color': '#d4c5a9'
        }
    };

    var themeNames = Object.keys(THEMES);
    var currentIndex = 0;

    function applyTheme(name) {
        var vars = THEMES[name];
        if (!vars) return;
        var root = document.documentElement;
        for (var key in vars) {
            if (vars.hasOwnProperty(key)) {
                root.style.setProperty(key, vars[key]);
            }
        }
        root.setAttribute('data-theme', name);
        var btn = document.getElementById('theme-toggle-btn');
        if (btn) btn.textContent = name.charAt(0).toUpperCase() + name.slice(1);
    }

    function cycleTheme() {
        currentIndex = (currentIndex + 1) % themeNames.length;
        applyTheme(themeNames[currentIndex]);
    }

    function init() {
        var container = document.getElementById('theme-switcher-container');
        if (!container) return;

        var btn = document.createElement('button');
        btn.id = 'theme-toggle-btn';
        btn.textContent = 'Light';
        btn.style.cssText = 'padding:6px 14px;border:1px solid var(--border-color);border-radius:4px;background:var(--bg-secondary);color:var(--text-primary);cursor:pointer;font-size:0.8rem;';
        btn.addEventListener('click', cycleTheme);
        container.appendChild(btn);

        var currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
        var idx = themeNames.indexOf(currentTheme);
        if (idx >= 0) currentIndex = idx;
        applyTheme(themeNames[currentIndex]);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
"""
