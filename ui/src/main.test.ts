// main.ts mounts the page; what is tested here is its wiring: the app it makes has the handler of errors set, and the window's listeners are on.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type * as VueModule from "vue";
import type { App } from "vue";

const made: App[] = [];

vi.mock("vue", async (importOriginal) => {
  const vue = await importOriginal<typeof VueModule>();
  return {
    ...vue,
    createApp: (...args: Parameters<typeof VueModule.createApp>) => {
      const app = vue.createApp(...args);
      made.push(app);
      return app;
    },
  };
});
vi.mock("./AccessGate.vue", () => ({ default: { render: () => null } }));
vi.mock("./lib/worker", () => ({ registerWorker: () => false }));

beforeEach(() => {
  made.length = 0;
  document.body.innerHTML = '<div id="app"></div>';
  vi.resetModules();
});
afterEach(() => vi.restoreAllMocks());

describe("main", () => {
  it("makes the page's app with the capture of errors in place before it mounts", async () => {
    const { pageErrors } = await import("@/lib/pageerrors");
    const record = vi.spyOn(pageErrors, "record");
    await import("./main");
    expect(made).toHaveLength(1);
    const handler = made[0]?.config.errorHandler;
    expect(handler).toBeTypeOf("function");
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    handler?.(new Error("in a component"), null, "setup function");
    expect(record).toHaveBeenCalledWith(expect.objectContaining({ message: "in a component" }), "vue", "");
    window.dispatchEvent(new ErrorEvent("error", { error: new Error("on the window"), message: "on the window" }));
    expect(record).toHaveBeenCalledWith(expect.objectContaining({ message: "on the window" }), "window");
  });
});
