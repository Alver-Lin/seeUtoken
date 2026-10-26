import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { resolve } from 'path';

export default defineConfig({
  plugins: [vue()],
  base: './',
  build: {
    outDir: resolve(__dirname, '../ui'),
    emptyOutDir: true,
    rollupOptions: {
      input: {
        panels: resolve(__dirname, 'panels/index.html'),
        dashboard: resolve(__dirname, 'dashboard/index.html'),
        float: resolve(__dirname, 'float/index.html'),
      },
    },
  },
  server: {
    port: 5173,
  },
});
