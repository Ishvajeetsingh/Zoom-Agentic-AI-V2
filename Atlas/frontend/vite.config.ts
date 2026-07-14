import { defineConfig } from "vite";
import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Mirror tsconfig.json "paths" so the bundler resolves "@/*" too.
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy API calls to the standalone Atlas backend during dev.
      // The Atlas backend itself forwards to Zoom Agentic AI; the
      // frontend never talks to Zoom Agentic AI directly.
      "/atlas": {
        target: "http://localhost:8090",
        changeOrigin: true,
      },
      "/health": {
        target: "http://localhost:8090",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
