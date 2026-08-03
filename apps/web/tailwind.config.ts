import type { Config } from 'tailwindcss';
import animate from 'tailwindcss-animate';

/**
 * Theme values are carried over verbatim from the legacy pages' inline
 * <style> blocks so the migrated UI is pixel-identical:
 *   --line  #e5e7eb   --muted #64748b   --text #0f172a
 * plus the gold radial page background and Noto Sans Thai.
 */
export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    container: {
      center: true,
      padding: '1rem',
    },
    extend: {
      fontFamily: {
        sans: ["'Noto Sans Thai'", 'system-ui', 'sans-serif'],
        // The logo lockup and avatar initials deliberately use a Latin stack.
        display: ['system-ui', "'Segoe UI'", 'Arial', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      colors: {
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
        /** Far East Fame Line gold — the page gradient and focus ring. */
        brand: {
          DEFAULT: '#f6cb38',
          400: '#fadd6a',
          300: '#fcea9f',
          200: '#fef6da',
          dot: '#f5c518',
        },
        /** Semantic status colours used by the settings + job UIs. */
        state: {
          ok: '#059669',
          warn: '#d97706',
          error: '#dc2626',
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      backgroundImage: {
        'page-gold':
          'radial-gradient(125% 88% at 50% 132%,#f6cb38 0%,#fadd6a 18%,#fcea9f 36%,#fef6da 56%,#ffffff 76%)',
      },
      boxShadow: {
        card: '0 1px 3px rgba(15,23,42,.05)',
        'card-lg': '0 10px 30px rgba(15,23,42,.08)',
        popup: '0 12px 32px rgba(15,23,42,.14)',
      },
      keyframes: {
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' },
        },
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
      },
    },
  },
  plugins: [animate],
} satisfies Config;
