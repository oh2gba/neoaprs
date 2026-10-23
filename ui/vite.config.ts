import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

// The page is built into ../neoaprs/page (scripts/build-page sets NEOAPRS_OUT to it), package data that the daemon serves as it is and the wheel carries; the built files are kept in git, so the machine that runs NeoAPRS needs no node.
export default defineConfig({
  plugins: [vue()],
  base: "./",
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    outDir: process.env.NEOAPRS_OUT || "dist",
    emptyOutDir: true,
    sourcemap: false,
    chunkSizeWarningLimit: 1200,
  },
  server: {
    proxy: {
      "/ws": { target: "ws://127.0.0.1:7303", ws: true },
      "/basemap.pmtiles": { target: "http://127.0.0.1:7303" },
      "/basemap-world.pmtiles": { target: "http://127.0.0.1:7303" },
    },
  },
  test: {
    environment: "happy-dom",
    environmentOptions: { happyDOM: { url: "http://127.0.0.1:7303/" } },
    include: ["src/**/*.test.ts"],
    coverage: {
      provider: "v8",
      include: ["src/lib/**/*.ts", "src/composables/**/*.ts", "src/components/**/*.vue"],
      exclude: ["**/*.test.ts", "src/test/**"],
      reporter: ["text"],
    },
  },
});
