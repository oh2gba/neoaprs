import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { readFileSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";

/** The version of the package the page is built with: VERSION of neoaprs/__init__.py, the one place it is written. The page compares it with the daemon's. */
function packageVersion(): string {
  const text = readFileSync(fileURLToPath(new URL("../neoaprs/__init__.py", import.meta.url)), "utf-8");
  const found = /^VERSION\s*=\s*"([^"]+)"/m.exec(text);
  if (!found?.[1]) throw new Error("no VERSION in neoaprs/__init__.py");
  return found[1];
}

// The page is built into ../neoaprs/page (scripts/build-page sets NEOAPRS_OUT to it), package data that the daemon serves as it is and the wheel carries; the built files are kept in git, so the machine that runs NeoAPRS needs no node.
export default defineConfig({
  plugins: [vue()],
  define: { __PAGE_VERSION__: JSON.stringify(packageVersion()) },
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
      "/access": { target: "http://127.0.0.1:7303" },
      "/basemap.pmtiles": { target: "http://127.0.0.1:7303" },
      "/basemap-world.pmtiles": { target: "http://127.0.0.1:7303" },
    },
  },
  test: {
    environment: "happy-dom",
    environmentOptions: { happyDOM: { url: "http://127.0.0.1:7303/" } },
    include: ["src/**/*.test.ts"],
    setupFiles: ["src/test/setup.ts"],
    coverage: {
      provider: "v8",
      include: ["src/lib/**/*.ts", "src/composables/**/*.ts", "src/components/**/*.vue"],
      exclude: ["**/*.test.ts", "src/test/**"],
      reporter: ["text"],
    },
  },
});
