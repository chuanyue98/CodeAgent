import typography from '@tailwindcss/typography'
import colors from 'tailwindcss/colors'
import plugin from 'tailwindcss/plugin'

const STEPS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950]

// Palettes the pages still reference by name (bg-amber-50, text-red-700 ...).
// Each step is a CSS variable, so one class follows the theme: in dark the
// scale runs backwards (50 <-> 950), which keeps "tinted background + strong
// text" pairs legible without touching the call sites.
const HUES = [
  'amber', 'red', 'emerald', 'green', 'sky', 'orange', 'blue', 'violet',
  'indigo', 'yellow', 'cyan', 'purple', 'rose', 'pink',
]

// slate is the neutral the pages lean on most. Its dark scale is hand-set to
// the console's surfaces rather than mirrored: mirroring would put the faint
// text steps (400/500) at contrast the dark ground can't carry.
const SLATE_DARK = {
  50: '#13161b', 100: '#1a1e25', 200: '#242a33', 300: '#333b47', 400: '#7c8593',
  500: '#8f97a5', 600: '#a6adb9', 700: '#c1c6cf', 800: '#dfe2e8', 900: '#eceef2', 950: '#f5f6f8',
}

const channels = hex => {
  const n = parseInt(hex.slice(1), 16)
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`
}

const scale = name =>
  Object.fromEntries(STEPS.map(step => [step, `rgb(var(--c-${name}-${step}) / <alpha-value>)`]))

const themeScales = plugin(({ addBase }) => {
  const light = { '--c-white': '255 255 255' }
  const dark = { '--c-white': '19 22 27' }
  for (const step of STEPS) {
    light[`--c-slate-${step}`] = channels(colors.slate[step])
    dark[`--c-slate-${step}`] = channels(SLATE_DARK[step])
  }
  for (const hue of HUES) {
    STEPS.forEach((step, i) => {
      light[`--c-${hue}-${step}`] = channels(colors[hue][step])
      dark[`--c-${hue}-${step}`] = channels(colors[hue][STEPS[STEPS.length - 1 - i]])
    })
  }
  // Dark-first: bare :root is dark, light is the opt-in (OS preference or an
  // explicit data-theme), mirroring the semantic tokens in index.css.
  addBase({
    ':root': dark,
    '@media (prefers-color-scheme: light)': { ':root:not([data-theme="dark"])': light },
    ':root[data-theme="light"]': light,
  })
})

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary) / <alpha-value>)",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive) / <alpha-value>)",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Semantic status hues, separate from the accent.
        ok: "rgb(var(--ok) / <alpha-value>)",
        warn: "rgb(var(--warn) / <alpha-value>)",
        // The terminal and code blocks stay dark in both themes.
        term: {
          DEFAULT: "#0a0c0f",
          fg: "#d5d9e0",
          dim: "#6b7482",
          line: "#1c2129",
        },
        // One hue per engine, used the same way everywhere an engine is named.
        engine: {
          claude: "rgb(var(--engine-claude) / <alpha-value>)",
          opencode: "rgb(var(--engine-opencode) / <alpha-value>)",
          codex: "rgb(var(--engine-codex) / <alpha-value>)",
          codebuddy: "rgb(var(--engine-codebuddy) / <alpha-value>)",
          antigravity: "rgb(var(--engine-antigravity) / <alpha-value>)",
        },
        white: "rgb(var(--c-white) / <alpha-value>)",
        slate: scale('slate'),
        ...Object.fromEntries(HUES.map(hue => [hue, scale(hue)])),
      },
      fontFamily: {
        sans: [
          '"Instrument Sans"',
          "-apple-system",
          "BlinkMacSystemFont",
          '"Segoe UI"',
          "Roboto",
          '"PingFang SC"',
          '"Microsoft YaHei"',
          "sans-serif",
        ],
        mono: [
          '"Geist Mono"',
          '"JetBrains Mono"',
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          '"PingFang SC"',
          '"Microsoft YaHei"',
          "monospace",
        ],
      },
      // 2xl/3xl hang off --radius so surfaces share one corner source.
      borderRadius: {
        "2xl": "var(--radius)",
        "3xl": "calc(var(--radius) + 0.25rem)",
      },
      // Markdown colours follow the theme through the same variables as the
      // rest of the app; use `prose prose-ca` instead of prose-slate/invert.
      typography: {
        ca: {
          css: {
            '--tw-prose-body': 'hsl(var(--foreground) / 0.85)',
            '--tw-prose-headings': 'hsl(var(--foreground))',
            '--tw-prose-lead': 'hsl(var(--muted-foreground))',
            '--tw-prose-links': 'hsl(var(--primary))',
            '--tw-prose-bold': 'hsl(var(--foreground))',
            '--tw-prose-counters': 'hsl(var(--muted-foreground))',
            '--tw-prose-bullets': 'hsl(var(--muted-foreground))',
            '--tw-prose-hr': 'hsl(var(--border))',
            '--tw-prose-quotes': 'hsl(var(--foreground))',
            '--tw-prose-quote-borders': 'hsl(var(--border))',
            '--tw-prose-captions': 'hsl(var(--muted-foreground))',
            '--tw-prose-code': 'hsl(var(--foreground))',
            '--tw-prose-pre-code': '#d5d9e0',
            '--tw-prose-pre-bg': '#0a0c0f',
            '--tw-prose-th-borders': 'hsl(var(--border))',
            '--tw-prose-td-borders': 'hsl(var(--border))',
          },
        },
      },
      transitionTimingFunction: {
        "out-expo": "cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [
    typography,
    themeScales,
  ],
}
