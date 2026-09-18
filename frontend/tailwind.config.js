/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: { space: '#0B0F17', cyan: '#00F0FF', violet: '#7000FF', danger: '#FF0055' },
      fontFamily: { sans: ['Inter', 'Segoe UI', 'Arial', 'sans-serif'], mono: ['Consolas', 'monospace'] },
    },
  },
  plugins: [],
};
