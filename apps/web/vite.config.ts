import { defineConfig } from 'vite';
import preact from '@preact/preset-vite';
import { VitePWA } from 'vite-plugin-pwa';

// base './' + hash routing: the same build works from GitHub Pages, a file
// server, or inside the Capacitor WebView.
export default defineConfig({
  base: './',
  plugins: [
    preact(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: null,
      includeAssets: ['icon.svg', 'samples/*.jpg', 'calibration_mat.pdf'],
      manifest: {
        name: 'Parakh — onion lot assay',
        short_name: 'Parakh',
        description: 'Measure an onion lot with a phone camera, grade it by a published rule pack, and issue a verifiable receipt. Works offline.',
        theme_color: '#f6f1e9',
        background_color: '#f6f1e9',
        display: 'standalone',
        orientation: 'portrait',
        start_url: './',
        scope: './',
        icons: [
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,jpg,woff2,json,pdf,onnx,wasm}'],
        maximumFileSizeToCacheInBytes: 30 * 1024 * 1024,
        navigateFallback: 'index.html',
      },
    }),
  ],
  worker: { format: 'es' },
  build: { target: 'es2022', chunkSizeWarningLimit: 1500 },
  server: { host: true },
});
