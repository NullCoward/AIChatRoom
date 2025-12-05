/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Match the desktop app dark theme
        'chat-bg': '#1a1a2e',
        'panel-bg': '#16213e',
        'card-bg': '#1f2937',
        'accent': '#3b82f6',
        'success': '#7ee787',
        'warning': '#ffa657',
        'info': '#79c0ff',
      },
      fontFamily: {
        mono: ['Consolas', 'Monaco', 'monospace'],
      },
    },
  },
  plugins: [],
}
