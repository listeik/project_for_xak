import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': 'http://localhost:8000' } },
  build: {
    rollupOptions: {
      output: { manualChunks: { echarts: ['echarts'], react: ['react', 'react-dom'] } },
    },
  },
});
