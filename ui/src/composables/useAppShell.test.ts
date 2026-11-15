// What the shell puts in the page's context about the radios (composables/useAppShell.ts): `radiosNamed` (several radios on: plan section 6's rule, where it was "the HF radio is on", plan section 9) and
// `connected` (any radio that is on has its line up: what Send and the station's questions wait for). Read from the context a pane of the page is given, on the page mounted as the App tests mount it.
import "@/test/mockmap";
import { flushPromises } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SidePanel from "@/components/SidePanel.vue";
import { DAEMON_KEY, type DaemonContext } from "@/composables/useDaemonContext";
import type { RadioRow } from "@/protocol/protocol";
import { open, useAppHarness } from "@/test/app";
import { configValues, radioRow, tncState } from "@/test/fixtures";

useAppHarness();

/** The page told these radios (and the FM radio's topic of before in that state), and the context its panes read. */
async function shellWith(rows: RadioRow[], fm: ReturnType<typeof tncState> = tncState()): Promise<DaemonContext> {
  const { wrapper, socket } = await open();
  socket.say({ type: "state", topic: "config", rev: 1, value: configValues({ "fm/enabled": "true", "hf/enabled": "false" }) });
  socket.say({ type: "state", topic: "tnc", rev: 1, value: fm });
  socket.say({ type: "state", topic: "radios", rev: 0, value: Object.fromEntries(rows.map((row) => [String(row.id), row])) });
  await flushPromises();
  const pane = wrapper.findComponent(SidePanel);
  return (pane.vm.$ as unknown as { provides: Record<symbol, DaemonContext> }).provides[DAEMON_KEY as symbol];
}

const down = { state: "waiting", problem: { code: "radio.not_connected", params: {} } } as const;

describe("the shell's context with any number of radios", () => {
  it("names the radios while two FM radios are on and no HF radio, and not while one is", async () => {
    const two = await shellWith([
      radioRow(1, "kenwood-tnc2"),
      radioRow(2, "mercury", { enabled: false, state: "stopped" }),
      radioRow(3, "kiss", { number: 2 }),
    ]);
    expect(two.radiosNamed.value).toBe(true);
    const one = await shellWith([
      radioRow(1, "kenwood-tnc2"),
      radioRow(2, "mercury", { enabled: false, state: "stopped" }),
      radioRow(3, "kiss", { number: 2, enabled: false, state: "stopped" }),
    ]);
    expect(one.radiosNamed.value).toBe(false);
  });

  it("is connected while any radio that is on has its line up, radio 3 alone among them", async () => {
    const third = await shellWith(
      [radioRow(1, "kenwood-tnc2", down), radioRow(2, "mercury", { enabled: false, state: "stopped" }), radioRow(3, "kiss", { number: 2 })],
      tncState({ state: "waiting", problem: "no radio found" }),
    );
    expect(third.connected.value).toBe(true);
  });

  it("is not connected while no radio that is on is, whatever a removed radio's row still says", async () => {
    const none = await shellWith(
      [
        radioRow(1, "kenwood-tnc2", down),
        radioRow(2, "mercury", { enabled: false, state: "stopped" }),
        radioRow(3, "kiss", { number: 2, ...down }),
        radioRow(4, "kiss", { number: 3, removed: true, enabled: false, state: "connected" }),
      ],
      tncState({ state: "waiting", problem: "no radio found" }),
    );
    expect(none.connected.value).toBe(false);
  });
});
