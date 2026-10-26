import { defineConfig, type Plugin } from "vite";
import vue from "@vitejs/plugin-vue";
import { createHash } from "node:crypto";
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath, URL } from "node:url";

/** The build of the page as the service worker names its caches by: a hash of every file the build wrote (not sw.js itself), so that it changes when any file the page ships does and by nothing else, not by the version of NeoAPRS. */
function buildOf(folder: string): string {
  const files = readdirSync(folder, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => relative(folder, join(entry.parentPath, entry.name)).split(sep).join("/"))
    .filter((name) => name !== "sw.js")
    .sort();
  const hash = createHash("sha256");
  for (const name of files)
    hash
      .update(name)
      .update("\0")
      .update(readFileSync(join(folder, name)))
      .update("\0");
  return hash.digest("hex").slice(0, 10);
}

/** sw/sw.js, the service worker, is written out as sw.js at the root of the page (its scope is all of it), once everything else is written, with the build of the page in it: a changed page is a different worker file, which the browser takes as an update, and a version of NeoAPRS that changed no file of the page is not. */
function serviceWorker(): Plugin {
  return {
    name: "neoaprs-service-worker",
    apply: "build",
    writeBundle(options) {
      const folder = options.dir ?? "";
      const source = readFileSync(fileURLToPath(new URL("./sw/sw.js", import.meta.url)), "utf-8");
      writeFileSync(join(folder, "sw.js"), source.replaceAll("__PAGE_BUILD__", buildOf(folder)));
    },
  };
}

// The page is built into ../neoaprs/page (scripts/build-page sets NEOAPRS_OUT to it), package data that the daemon serves as it is and the wheel carries; the built files are kept in git, so the machine that runs NeoAPRS needs no node.
export default defineConfig({
  plugins: [vue(), serviceWorker()],
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
      include: [
        "src/lib/**/*.ts",
        "src/composables/**/*.ts",
        "src/components/**/*.vue",
        "src/help/**/*.{ts,vue}",
        "src/protocol/**/*.ts",
        "src/App.vue",
        "src/AccessGate.vue",
        "src/main.ts",
      ],
      exclude: ["**/*.test.ts", "src/test/**"],
      reporter: ["text"],
    },
  },
});
