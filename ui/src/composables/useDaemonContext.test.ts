import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { fakeDaemon, withDaemon } from "@/test/context";

const Reader = (seen: (context: ReturnType<typeof useDaemonContext>) => void) =>
  defineComponent({
    setup() {
      seen(useDaemonContext());
      return () => h("div");
    },
  });

describe("useDaemonContext", () => {
  it("is what the page provided", () => {
    const daemon = fakeDaemon();
    let seen: unknown;
    mount(
      Reader((context) => (seen = context)),
      { global: withDaemon(daemon) },
    );
    expect(seen).toBe(daemon);
  });

  it("is an error in a pane mounted where the page gave none", () => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    expect(() => mount(Reader(() => undefined))).toThrow("not provided");
    vi.restoreAllMocks();
  });
});
