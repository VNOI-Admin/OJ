(function() {
    'use strict';

    const THEME_KEY = 'vnoj-theme-preference';
    const THEME_LIGHT = 'light';
    const THEME_DARK = 'dark';
    const THEME_AUTO = 'auto';

    class ThemeManager {
        constructor() {
            this.currentTheme = this.getStoredTheme() || THEME_AUTO;
            this.init();
        }

        init() {
            // Apply theme on load
            this.applyTheme(this.currentTheme);

            // Listen for system theme changes
            if (window.matchMedia) {
                window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
                    if (this.currentTheme === THEME_AUTO) {
                        this.applyTheme(THEME_AUTO);
                    }
                });
            }
        }

        getStoredTheme() {
            try {
                return localStorage.getItem(THEME_KEY);
            } catch (e) {
                return null;
            }
        }

        setStoredTheme(theme) {
            try {
                localStorage.setItem(THEME_KEY, theme);
            } catch (e) {
                console.warn('Failed to save theme preference');
            }
        }

        getSystemTheme() {
            if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
                return THEME_DARK;
            }
            return THEME_LIGHT;
        }

        getEffectiveTheme(theme) {
            if (theme === THEME_AUTO) {
                return this.getSystemTheme();
            }
            return theme;
        }

        applyTheme(theme) {
            const effectiveTheme = this.getEffectiveTheme(theme);
            const isDark = effectiveTheme === THEME_DARK;

            // Update data attribute on body
            document.body.setAttribute('data-theme', effectiveTheme);

            // Update main stylesheet links
            const lightStylesheet = document.querySelector('link[href*="style.css"]:not([href*="dark"])');
            const darkStylesheet = document.querySelector('link[href*="dark/style.css"]');

            if (lightStylesheet && darkStylesheet) {
                if (isDark) {
                    lightStylesheet.media = 'not all';
                    darkStylesheet.media = 'all';
                } else {
                    lightStylesheet.media = 'all';
                    darkStylesheet.media = 'not all';
                }
            }

            // Update blog-specific stylesheets if they exist
            this.updateBlogStylesheets(isDark);

            // Update button icon
            this.updateToggleButton(theme);

            // Dispatch custom event for other scripts to listen to
            window.dispatchEvent(new CustomEvent('themechange', {
                detail: { theme: effectiveTheme }
            }));
        }

        updateBlogStylesheets(isDark) {
            // Blog modern list styles
            const blogModernLight = document.getElementById('blog-modern-light');
            const blogModernDark = document.getElementById('blog-modern-dark');
            
            if (blogModernLight && blogModernDark) {
                if (isDark) {
                    blogModernLight.media = 'not all';
                    blogModernDark.media = 'all';
                } else {
                    blogModernLight.media = 'all';
                    blogModernDark.media = 'not all';
                }
            }

            // Blog post detail styles
            const blogPostLight = document.getElementById('blog-post-light');
            const blogPostDark = document.getElementById('blog-post-dark');
            
            if (blogPostLight && blogPostDark) {
                if (isDark) {
                    blogPostLight.media = 'not all';
                    blogPostDark.media = 'all';
                } else {
                    blogPostLight.media = 'all';
                    blogPostDark.media = 'not all';
                }
            }
        }

        updateToggleButton(theme) {
            const button = document.getElementById('theme-toggle-btn');
            if (!button) return;

            const icon = button.querySelector('i');
            const text = button.querySelector('.theme-toggle-text');

            // Update icon based on current theme
            if (icon) {
                icon.className = ''; // Clear existing classes
                if (theme === THEME_LIGHT) {
                    icon.className = 'fa fa-sun-o';
                } else if (theme === THEME_DARK) {
                    icon.className = 'fa fa-moon-o';
                } else {
                    icon.className = 'fa fa-adjust';
                }
            }

            // Update text if present
            if (text) {
                const labels = {
                    [THEME_LIGHT]: 'Light',
                    [THEME_DARK]: 'Dark',
                    [THEME_AUTO]: 'Auto'
                };
                text.textContent = labels[theme] || 'Auto';
            }

            // Update aria-label
            button.setAttribute('aria-label', `Theme: ${theme}`);
        }

        toggle() {
            // Cycle through: auto -> light -> dark -> auto
            const themeSequence = [THEME_AUTO, THEME_LIGHT, THEME_DARK];
            const currentIndex = themeSequence.indexOf(this.currentTheme);
            const nextIndex = (currentIndex + 1) % themeSequence.length;
            const nextTheme = themeSequence[nextIndex];

            this.setTheme(nextTheme);
        }

        setTheme(theme) {
            this.currentTheme = theme;
            this.setStoredTheme(theme);
            this.applyTheme(theme);
        }
    }

    // Initialize theme manager when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            window.themeManager = new ThemeManager();
        });
    } else {
        window.themeManager = new ThemeManager();
    }

    // Expose toggle function globally for button onclick
    window.toggleTheme = function() {
        if (window.themeManager) {
            window.themeManager.toggle();
        }
    };
})();
