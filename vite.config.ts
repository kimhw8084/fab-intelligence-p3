import { defineConfig } from "vitest/config";

export default defineConfig({
  root: "products/p3/reference_host",
  plugins: [],
  server: { host: "127.0.0.1", proxy: { "/api": "http://127.0.0.1:8765" } },
  build: { outDir: "static", emptyOutDir: true, sourcemap: false, target: "es2022" },
  test: {
    environment: "happy-dom",
    setupFiles: [],
    include: ["src/**/*.test.tsx", "../ui/**/*.test.tsx"],
  },
});
