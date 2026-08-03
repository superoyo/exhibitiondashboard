import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

/**
 * During the migration the FastAPI app (port 8000) is still the only backend
 * and the only thing that can serve /static/*. Proxying both keeps the React
 * dev server a drop-in replacement for opening the old pages directly.
 */
const LEGACY_BACKEND = process.env.VITE_PROXY_TARGET ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: LEGACY_BACKEND, changeOrigin: true },
      '/static': { target: LEGACY_BACKEND, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    // No production sourcemaps: they roughly quadruple the deployed size and are
    // served publicly, and there is no error-tracking service here to consume
    // them. `vite dev` always has full sourcemaps regardless.
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          // ECharts and SheetJS are heavy and only used by report/roster.
          // Splitting them keeps the login + home payload small.
          vendor: ['react', 'react-dom', 'react-router-dom'],
        },
      },
    },
  },
});
