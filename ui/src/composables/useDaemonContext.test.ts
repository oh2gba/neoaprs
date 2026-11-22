import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick } from "vue";
import { useDaemon } from "@/composables/useDaemon";
import { provideDaemon, useDaemonContext } from "@/composables/useDaemonContext";
import { useRadios } from "@/composables/useRadios";
import { fakeDaemon, withDaemon } from "@/test/context";
import { FakeSocket } from "@/test/fakesocket";
import { configValues, hello, radioRow, status } from "@/test/fixtures";

const Reader = (seen: (context: ReturnType<typeof useDaemonContext>) => void) =>
  defineComponent({
    setup() {
      seen(useDaemonContext());
      return () => h("div");
    },
  });

afterEach(() => vi.unstubAllGlobals());

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

  it("carries the radios as the daemon told them, none from a daemon that tells none, and a pane reads the radios from them, and the radio this page added once its row has come", async () => {
    FakeSocket.all = [];
    vi.stubGlobal("WebSocket", FakeSocket);
    let ids: number[] = [];
    let unheard: number | undefined;
    let made: number | undefined;
    const Pane = defineComponent({
      setup() {
        const { enabled, unheard: first, added } = useRadios();
        return () => {
          ids = enabled.value.map((radio) => radio.id);
          unheard = first.value?.id;
          made = added.value?.id;
          return h("div");
        };
      },
    });
    const Page = defineComponent({
      setup() {
        const daemon = useDaemon(() => "ws://host/ws");
        provideDaemon({
          ...fakeDaemon(),
          radios: daemon.radios,
          radioAdded: daemon.radioAdded,
          config: daemon.config,
          status: daemon.status,
          // The parts of the daemon the radios are read from, as the page spreads them in:
          // composables/useAppShell.ts.
        });
        return () => h(Pane);
      },
    });
    mount(Page);
    const socket = FakeSocket.last();
    socket.say(hello());
    socket.say({ type: "state", topic: "config", rev: 0, value: configValues() });
    await nextTick();
    expect([ids, unheard]).toEqual([[], undefined]);
    socket.say({
      type: "state",
      topic: "radios",
      rev: 0,
      value: {
        "2": radioRow(2, "mercury", { position: 1 }),
        "1": radioRow(1, "kenwood-tnc2", { position: 2 }),
        "3": radioRow(3, "kiss", { number: 2, position: 3 }),
      },
    });
    socket.say(status({ unheard_radio: 3 }));
    await nextTick();
    expect([ids, unheard]).toEqual([[2, 1, 3], 3]);
    socket.say({ type: "radio_added", id: 4 });
    await nextTick();
    expect(made).toBeUndefined();
    socket.say({ type: "patch", topic: "radios", rev: 1, ops: [{ op: "set", key: "4", value: radioRow(4, "dummy-hf", { number: 2, position: 4 }) }] });
    await nextTick();
    expect([ids, made]).toEqual([[2, 1, 3, 4], 4]);
  });

  it("is an error in a pane mounted where the page gave none", () => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    expect(() => mount(Reader(() => undefined))).toThrow("not provided");
    vi.restoreAllMocks();
  });
});
