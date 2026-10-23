// Imported first by a test that mounts the map: replaces the MapLibre loader of the page with the fake of test/fakemap.ts.
import { vi } from "vitest";

vi.mock("@/lib/basemap", async () => {
  const { fakeEngine, fakeState } = await import("@/test/fakemap");
  return {
    loadMapEngine: () => (fakeState.engine ? Promise.resolve(fakeEngine) : Promise.reject(new Error("no engine"))),
    archivesPresent: () => Promise.resolve({ detail: fakeState.archive, world: fakeState.world }),
    archiveUrl: (file = "basemap.pmtiles", version = "") => `http://127.0.0.1:7303/${file}${version ? `?v=${version}` : ""}`,
    glyphsUrl: () => "http://127.0.0.1:7303/fonts/{fontstack}/{range}.pbf",
  };
});
