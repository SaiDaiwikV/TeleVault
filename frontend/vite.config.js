import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api to the FastAPI backend (uvicorn on :8000) so the
// browser only ever talks to one origin and no CORS dance is needed locally.
// `npm run build` outputs to ../static/app so FastAPI can serve the built SPA
// directly in production (single deployable unit, no separate frontend host).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "../static/app",
    emptyOutDir: true,
  },
  test: {
    // Use jsdom so React components can render in a DOM-like environment.
    environment: "jsdom",
    globals: true,
    // Auto-import @testing-library/jest-dom matchers for every test file.
    setupFiles: "./src/test/setup.js",
    // Exclude node_modules and the Vite build output.
    exclude: ["node_modules/**", "../static/**"],
  },
});
