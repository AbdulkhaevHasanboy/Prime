/** @type {import('tailwindcss').Config} */

/*
 * Tailwind drives the public marketing pages (LandingPage.vue) only.
 *
 * Preflight (Tailwind's global reset) is DISABLED on purpose: the rest of the
 * app is styled with hand-written scoped CSS + the design system in
 * src/assets/main.css, and a global reset would clobber it. Utilities here are
 * opt-in by class, so they never touch a component that doesn't use them. The
 * small reset the landing needs lives scoped inside LandingPage.vue.
 *
 * The theme below is a 1:1 port of the inline `tailwind.config` that used to
 * live in the old landing.html (Material 3 token palette + type scale).
 */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      colors: {
        /* Dark app theme — bound to the CSS variables in src/assets/main.css so
           theming stays centralized. Used by the dashboard views (not landing). */
        ink: 'var(--text-primary)',
        'ink-soft': 'var(--text-secondary)',
        'ink-mute': 'var(--text-muted)',
        brand: 'var(--primary)',
        'brand-hover': 'var(--primary-hover)',

        'surface-container-lowest': '#ffffff',
        outline: '#777587',
        'surface-bright': '#f7f9fb',
        'on-surface-variant': '#464555',
        'on-primary-container': '#dad7ff',
        'on-surface': '#191c1e',
        'on-primary': '#ffffff',
        'on-secondary': '#ffffff',
        'on-error-container': '#93000a',
        'secondary-container': '#57dffe',
        surface: '#f7f9fb',
        'inverse-on-surface': '#eff1f3',
        'on-primary-fixed-variant': '#3323cc',
        'primary-fixed': '#e2dfff',
        'tertiary-fixed': '#ffdadb',
        error: '#ba1a1a',
        'primary-container': '#4f46e5',
        'on-error': '#ffffff',
        'surface-tint': '#4f46e5',
        'on-secondary-fixed-variant': '#004e5c',
        'surface-variant': '#e0e3e5',
        'primary-fixed-dim': '#c3c0ff',
        'tertiary-container': '#bf0f3c',
        'inverse-surface': '#2d3133',
        'on-tertiary': '#ffffff',
        'secondary-fixed': '#acedff',
        'error-container': '#ffdad6',
        'tertiary-fixed-dim': '#ffb2b7',
        'outline-variant': '#c7c4d8',
        'surface-dim': '#d8dadc',
        secondary: '#06b6d4',
        primary: '#4f46e5',
        tertiary: '#95002b',
        'on-tertiary-fixed-variant': '#92002a',
        background: '#f7f9fb',
        'on-secondary-container': '#006172',
        'secondary-fixed-dim': '#4cd7f6',
        'inverse-primary': '#c3c0ff',
        'surface-container': '#eceef0',
        'on-background': '#191c1e',
        'on-secondary-fixed': '#001f26',
        'surface-container-high': '#e6e8ea',
        'surface-container-low': '#f2f4f6',
        'surface-container-highest': '#e0e3e5',
        'on-primary-fixed': '#0f0069',
        'on-tertiary-fixed': '#40000d',
        'on-tertiary-container': '#ffd0d2',
      },
      borderRadius: {
        DEFAULT: '0.25rem',
        lg: '0.5rem',
        xl: '0.75rem',
        full: '9999px',
      },
      spacing: {
        'container-max': '1280px',
        'margin-desktop': '48px',
        'margin-mobile': '20px',
        gutter: '24px',
        base: '8px',
      },
      maxWidth: {
        'container-max': '1280px',
      },
      fontFamily: {
        /* Dark app theme fonts (bound to main.css variables). */
        display: ['var(--font-display)', 'sans-serif'],
        body: ['var(--font-primary)', 'sans-serif'],
        'display-lg': ['Lexend', 'sans-serif'],
        'body-md': ['Inter', 'sans-serif'],
        'label-caps': ['Geist', 'sans-serif'],
        'headline-md': ['Lexend', 'sans-serif'],
        'body-lg': ['Inter', 'sans-serif'],
        'display-lg-mobile': ['Lexend', 'sans-serif'],
      },
      fontSize: {
        'display-lg': ['48px', { lineHeight: '56px', letterSpacing: '-0.02em', fontWeight: '700' }],
        'body-md': ['16px', { lineHeight: '24px', fontWeight: '400' }],
        'label-caps': ['12px', { lineHeight: '16px', letterSpacing: '0.05em', fontWeight: '600' }],
        'headline-md': ['24px', { lineHeight: '32px', fontWeight: '600' }],
        'body-lg': ['18px', { lineHeight: '28px', fontWeight: '400' }],
        'display-lg-mobile': ['32px', { lineHeight: '40px', letterSpacing: '-0.02em', fontWeight: '700' }],
      },
    },
  },
  plugins: [],
}
