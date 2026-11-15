// The counting of who looks at a radio's scope (composables/useScopeLooks.ts): the rows are asked for while at least one pane looks, the page is in front, the radio has a scope (on, its type has one, its modem the interface) and
// the socket is open, and not otherwise; every radio looked at at once, in frames that name their radio; the page keeps each radio's rows apart (composables/useScopeRows.ts), and the monitor card's radio is the one
// chosen while it has a scope, else the first.
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick, shallowReactive, shallowRef } from "vue";
import { useScopeLooks } from "@/composables/useScopeLooks";
import { useScopeRows } from "@/composables/useScopeRows";
import type { Connection } from "@/lib/hub";
import { BINS } from "@/lib/waterfall";
import type { PacketRow, RadioRow } from "@/protocol/protocol";
import { hfState, packet, radioRow, radiosTopic } from "@/test/fixtures";

function setup(scope = true) {
  const send = vi.fn((_command: unknown) => true);
  const hf = shallowRef(hfState());
  if (hf.value.modem) hf.value = { ...hf.value, modem: { ...hf.value.modem, scope } };
  const connection = shallowRef<Connection>("open");
  const visible = shallowRef(true);
  const looks = useScopeLooks(send, hf, connection, visible);
  /** A pane that looks while `looking` is true. */
  const pane = (looking: { value: boolean }) =>
    mount(
      defineComponent({
        setup() {
          looks.look(() => looking.value);
          return () => h("div");
        },
      }),
    );
  const asked = () => send.mock.calls.map(([c]) => c);
  return { looks, pane, asked, connection, visible };
}

describe("who looks at the scope", () => {
  it("asks for the rows when the first pane looks, once for two, and stops when the last one stops", async () => {
    const { looks, pane, asked } = setup();
    const a = shallowRef(false);
    const b = shallowRef(true);
    pane(a);
    pane(b);
    expect(looks.lookers.value).toBe(1);
    expect(asked()).toEqual([{ cmd: "radio_scope", radio: 2, on: true, named: true }]);
    a.value = true;
    await nextTick();
    expect(looks.lookers.value).toBe(2);
    expect(asked()).toHaveLength(1);
    b.value = false;
    await nextTick();
    expect(asked()).toHaveLength(1);
    a.value = false;
    await nextTick();
    expect(looks.lookers.value).toBe(0);
    expect(asked().at(-1)).toEqual({ cmd: "radio_scope", radio: 2, on: false, named: true });
  });

  it("takes a pane that goes away out of the count, and asks no more when it was the last", () => {
    const { looks, pane, asked } = setup();
    const wrapper = pane(shallowRef(true));
    expect(looks.wanted.value).toBe(true);
    wrapper.unmount();
    expect(looks.lookers.value).toBe(0);
    expect(asked().at(-1)).toEqual({ cmd: "radio_scope", radio: 2, on: false, named: true });
  });

  it("asks for nothing while the page is hidden, and when the modem has no scope", () => {
    const hidden = setup();
    hidden.visible.value = false;
    hidden.pane(shallowRef(true));
    expect(hidden.looks.wanted.value).toBe(false);
    expect(hidden.asked()).toEqual([]);
    hidden.visible.value = true;
    expect(hidden.asked()).toEqual([{ cmd: "radio_scope", radio: 2, on: true, named: true }]);
    const none = setup(false);
    none.pane(shallowRef(true));
    expect(none.looks.available.value).toBe(false);
    expect(none.asked()).toEqual([]);
  });

  it("asks again when the socket is open anew, and says nothing to a closed one", async () => {
    const { pane, asked, connection } = setup();
    pane(shallowRef(true));
    connection.value = "closed";
    await nextTick();
    expect(asked()).toHaveLength(1);
    connection.value = "open";
    await nextTick();
    expect(asked()).toEqual([
      { cmd: "radio_scope", radio: 2, on: true, named: true },
      { cmd: "radio_scope", radio: 2, on: true, named: true },
    ]);
  });
});

/** A Mercury radio whose modem has the interface (or has not, `scope` false). */
const mercury = (id: number, extra: Partial<RadioRow> = {}, scope = true): RadioRow => {
  const modem = hfState().modem!;
  return radioRow(id, "mercury", { modem: { ...modem, scope }, ...extra });
};

function byRadio(...rows: RadioRow[]) {
  const send = vi.fn((_command: unknown) => true);
  const radios = shallowRef<ReadonlyMap<string, RadioRow> | null>(radiosTopic(...rows));
  const clock = { now: Date.UTC(2026, 10, 15, 12, 0, 0) };
  const packets = shallowReactive(new Map<string, PacketRow>());
  const rows_ = useScopeRows(packets, undefined, () => clock.now);
  const connection = shallowRef<Connection>("open");
  const visible = shallowRef(true);
  const looks = useScopeLooks(send, shallowRef(null), connection, visible, { radios });
  /** A pane that looks at `radio` (none: the first with a scope) while `looking` is true. */
  const pane = (looking: { value: boolean }, radio?: { value: number | null }) =>
    mount(
      defineComponent({
        setup() {
          looks.look(() => looking.value, radio && (() => radio.value));
          return () => h("div");
        },
      }),
    );
  const asked = () => send.mock.calls.map(([c]) => c);
  return { looks, pane, asked, radios, rows: rows_, packets, clock, connection, visible };
}

describe("the scope by radio", () => {
  beforeEach(() => localStorage.clear());

  it("is there for each radio that is on, of a type with a scope and whose modem has the interface, in the order of their boxes", () => {
    const { looks, radios } = byRadio(
      radioRow(1, "kenwood-tnc2"),
      mercury(5, { position: 3 }),
      mercury(3, { position: 2 }),
      mercury(4, { enabled: false, state: "stopped" }),
      mercury(6, { removed: true, enabled: false }),
      mercury(7, {}, false),
      radioRow(8, "dummy-hf"),
    );
    expect(looks.radios.value).toEqual([3, 5]);
    expect(looks.available.value).toBe(true);
    expect([3, 4, 5, 6, 7, 8, 1].map(looks.has)).toEqual([true, false, true, false, false, false, false]);
    radios.value = radiosTopic(radioRow(1, "kenwood-tnc2"), mercury(3, {}, false));
    expect(looks.radios.value).toEqual([]);
    expect(looks.available.value).toBe(false);
  });

  it("without the topic `radios` (the wire of before) has the scope of the HF radio of before as the topic `hf` says it", () => {
    const { looks } = setup();
    expect(looks.radios.value).toEqual([2]);
    expect(setup(false).looks.radios.value).toEqual([]);
  });

  it("asks for the rows of each radio looked at, at once and each in frames that name it, and stops each when the last pane of it stops", async () => {
    const { pane, asked, looks } = byRadio(mercury(2), mercury(5));
    const a = shallowRef(true);
    const b = shallowRef(false);
    pane(a, shallowRef(2));
    pane(b, shallowRef(5));
    expect(asked()).toEqual([{ cmd: "radio_scope", radio: 2, on: true, named: true }]);
    b.value = true;
    await nextTick();
    expect(looks.asked.value).toEqual([2, 5]);
    expect(looks.lookers.value).toBe(2);
    expect(asked().slice(1)).toEqual([{ cmd: "radio_scope", radio: 5, on: true, named: true }]); // (radio 2's go on: nothing is asked again)
    b.value = false;
    await nextTick();
    expect(asked().slice(2)).toEqual([{ cmd: "radio_scope", radio: 5, on: false, named: true }]);
    a.value = false;
    await nextTick();
    expect(asked().at(-1)).toEqual({ cmd: "radio_scope", radio: 2, on: false, named: true });
    expect(looks.asked.value).toEqual([]);
    expect(looks.wanted.value).toBe(false);
  });

  it("asks once for two panes of one radio, and a pane that names no radio looks at the first with a scope", async () => {
    const { pane, asked } = byRadio(radioRow(1, "kenwood-tnc2"), mercury(4, { position: 1 }), mercury(9, { position: 2 }));
    const one = pane(shallowRef(true));
    pane(shallowRef(true), shallowRef(4));
    expect(asked()).toEqual([{ cmd: "radio_scope", radio: 4, on: true, named: true }]);
    one.unmount();
    await nextTick();
    expect(asked()).toHaveLength(1);
  });

  it("stops the rows of a radio that has no scope now (off, removed, its modem without the interface), and goes on with the others", async () => {
    const { pane, asked, radios } = byRadio(mercury(2), mercury(5));
    pane(shallowRef(true), shallowRef(2));
    pane(shallowRef(true), shallowRef(5));
    expect(asked()).toEqual([
      { cmd: "radio_scope", radio: 2, on: true, named: true },
      { cmd: "radio_scope", radio: 5, on: true, named: true },
    ]);
    radios.value = radiosTopic(mercury(2), mercury(5, { removed: true, enabled: false }));
    await nextTick();
    expect(asked().slice(2)).toEqual([{ cmd: "radio_scope", radio: 5, on: false, named: true }]);
    radios.value = radiosTopic(mercury(2, { enabled: false, state: "stopped" }));
    await nextTick();
    expect(asked().at(-1)).toEqual({ cmd: "radio_scope", radio: 2, on: false, named: true });
  });

  it("keeps each radio's rows apart, by the radio the frame names, and keeps them when nobody looks any more: a picture opened again is whole at once", async () => {
    const { pane, rows, looks } = byRadio(mercury(2), mercury(5));
    const row = () => ({ db: new Float32Array(BINS).fill(-40), level: -20, tx: false });
    const a = shallowRef(true);
    pane(a, shallowRef(2));
    pane(shallowRef(true), shallowRef(5));
    for (let i = 0; i < 3; i++) rows.hfScopeRow(row(), 2);
    rows.hfScopeRow(row(), 5);
    expect([rows.of(2).rows.length, rows.of(5).rows.length]).toEqual([3, 1]);
    expect(rows.of(2)).toBe(rows.memory); // (radio 2's is the memory of before)
    a.value = false;
    await nextTick();
    expect(looks.asked.value).toEqual([5]);
    expect(rows.of(2).rows).toHaveLength(3);
  });

  it("writes down the stations heard on each radio whose rows it keeps, with the SNR of the frame, in that radio's memory alone", async () => {
    const { rows, packets, clock } = byRadio(mercury(2), mercury(5));
    const heard = (id: number, radio: number, call: string, snr: number | null) =>
      packets.set(
        String(id),
        packet(id, { radio: "", radio_id: radio, source: call, snr, heard_at: new Date(clock.now).toISOString().replace(/\.\d+Z$/, "Z") }),
      );
    rows.of(5); // (a pane showed radio 5)
    heard(1, 5, "OH5AAA", 7);
    heard(2, 2, "OH2BBB", 3);
    heard(3, 1, "OH1CCC", null);
    await nextTick();
    expect(rows.of(5).heard.map((h) => [h.call, h.snr])).toEqual([["OH5AAA", 7]]);
    expect(rows.of(2).heard.map((h) => [h.call, h.snr])).toEqual([["OH2BBB", null]]); // (radio 2's SNR is its modem's, from the topic `hf`: none here)
  });

  it("shows on the monitor the radio chosen while it can have a scope, else the first that has one, and this browser remembers the choice", async () => {
    const { looks, radios } = byRadio(mercury(2), mercury(5));
    expect(looks.monitor.value).toBe(2);
    looks.showOnMonitor(5);
    expect(looks.monitor.value).toBe(5);
    await nextTick();
    expect(localStorage.getItem("NeoAPRS.monitorradio")).toBe("5");
    expect(byRadio(mercury(2), mercury(5)).looks.monitor.value).toBe(5);
    radios.value = radiosTopic(mercury(2), mercury(5, {}, false));
    expect(looks.monitor.value).toBe(5); // (its modem is without the interface for a moment: the card stays on it)
    for (const gone of [mercury(5, { enabled: false, state: "stopped" }), mercury(5, { removed: true, enabled: false }), radioRow(5, "dummy-hf")]) {
      radios.value = radiosTopic(mercury(2), mercury(5));
      expect(looks.monitor.value).toBe(5);
      radios.value = radiosTopic(mercury(2), gone);
      expect(looks.monitor.value).toBe(2);
    }
    radios.value = radiosTopic(mercury(2, { enabled: false, state: "stopped" }));
    expect(looks.monitor.value).toBeNull();
  });
});
