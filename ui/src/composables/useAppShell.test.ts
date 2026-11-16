// What the shell puts in the page's context about the radios (composables/useAppShell.ts): the topic `radios`, which the panes read as several radios on (plan section 6's rule) and
// `connected` (any radio that is on has its line up: what Send and the station's questions wait for). Read from the context a pane of the page is given, on the page mounted as the App tests mount it.
import "@/test/mockmap";
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { defineComponent } from "vue";
import SidePanel from "@/components/SidePanel.vue";
import { DAEMON_KEY, type DaemonContext } from "@/composables/useDaemonContext";
import type { RadioRow } from "@/protocol/protocol";
import { open, useAppHarness } from "@/test/app";
import { radioRow } from "@/test/fixtures";
import { useRadios } from "@/composables/useRadios";

useAppHarness();

/** The page told these radios, and the context its panes read. */
async function shellWith(rows: RadioRow[]): Promise<DaemonContext> {
  const { wrapper, socket } = await open();
  socket.say({ type: "state", topic: "radios", rev: 1, value: Object.fromEntries(rows.map((row) => [String(row.id), row])) });
  await flushPromises();
  const pane = wrapper.findComponent(SidePanel);
  return (pane.vm.$ as unknown as { provides: Record<symbol, DaemonContext> }).provides[DAEMON_KEY as symbol];
}

const down = { state: "waiting", problem: { code: "radio.not_connected", params: {} } } as const;

/** Whether the panes of the page read several radios on (composables/useRadios.ts `several`). */
function several(context: DaemonContext): boolean {
  let found = false;
  const probe = defineComponent({
    setup() {
      found = useRadios().several.value;
      return () => null;
    },
  });
  mount(probe, { global: { provide: { [DAEMON_KEY as symbol]: context } } });
  return found;
}

describe("the shell's context with any number of radios", () => {
  it("names the radios while two FM radios are on and no Mercury radio, and not while one is", async () => {
    const two = await shellWith([
      radioRow(1, "kenwood-tnc2"),
      radioRow(2, "mercury", { enabled: false, state: "stopped" }),
      radioRow(3, "kiss", { number: 2 }),
    ]);
    expect(several(two)).toBe(true);
    const one = await shellWith([
      radioRow(1, "kenwood-tnc2"),
      radioRow(2, "mercury", { enabled: false, state: "stopped" }),
      radioRow(3, "kiss", { number: 2, enabled: false, state: "stopped" }),
    ]);
    expect(several(one)).toBe(false);
  });

  it("is connected while any radio that is on has its line up, radio 3 alone among them", async () => {
    const third = await shellWith([
      radioRow(1, "kenwood-tnc2", down),
      radioRow(2, "mercury", { enabled: false, state: "stopped" }),
      radioRow(3, "kiss", { number: 2 }),
    ]);
    expect(third.connected.value).toBe(true);
  });

  it("is not connected while no radio that is on is, whatever a removed radio's row still says", async () => {
    const none = await shellWith([
      radioRow(1, "kenwood-tnc2", down),
      radioRow(2, "mercury", { enabled: false, state: "stopped" }),
      radioRow(3, "kiss", { number: 2, ...down }),
      radioRow(4, "kiss", { number: 3, removed: true, enabled: false, state: "connected" }),
    ]);
    expect(none.connected.value).toBe(false);
  });
});
