import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { defineComponent, h } from "vue";
import { useRadios, type Radios } from "@/composables/useRadios";
import { fakeDaemon, tell, withDaemon, type FakeDaemon } from "@/test/context";
import { heardBy, message, radioRow, radiosTopic as topic, station, status } from "@/test/fixtures";

/** What a pane reads of the radios: the one source. */
function read(context: FakeDaemon | null) {
  let seen: { radios: Radios } | undefined;
  const Reader = defineComponent({
    setup() {
      const radios = useRadios();
      return () => {
        seen = { radios };
        return h("div");
      };
    },
  });
  const wrapper = mount(Reader, context === null ? {} : { global: withDaemon(context) });
  return {
    wrapper,
    seen: () => {
      if (seen === undefined) throw new Error("not drawn");
      return seen;
    },
  };
}
const ids = (radios: { id: number }[]) => radios.map((radio) => radio.id);

const BOTH = topic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury"));

describe("useRadios", () => {
  it("has no radio before the daemon has told the topic `radios`", () => {
    const { seen } = read(fakeDaemon({ radios: null }));
    const { told, all, enabled, several, unheard, allowsPath, byId } = seen().radios;
    expect([told.value, all.value, enabled.value, several.value, unheard.value, allowsPath.value, byId(1)]).toEqual([
      false,
      [],
      [],
      false,
      null,
      false,
      undefined,
    ]);
  });

  it("reads the topic once it is told, follows it as it changes, and the radio of a call no radio heard from the status", async () => {
    const daemon = fakeDaemon({ radios: null });
    const { seen } = read(daemon);
    const { told, all, enabled, several, unheard, allowsPath, byId } = seen().radios;
    expect([told.value, ids(enabled.value), several.value]).toEqual([false, [], false]);
    await tell(daemon, {
      radios: topic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury", { position: 0 })),
      status: status({ unheard_radio: 1 }),
    });
    expect([
      told.value,
      ids(all.value),
      ids(enabled.value),
      several.value,
      unheard.value?.id,
      byId(2)?.row.type,
    ]).toEqual([true, [2, 1], [2, 1], true, 1, "mercury"]);
    await tell(daemon, {
      radios: topic(radioRow(1, "kenwood-tnc2", { enabled: false }), radioRow(2, "mercury")),
      status: status({ unheard_radio: 2 }),
    });
    expect([ids(enabled.value), several.value, unheard.value?.id, allowsPath.value]).toEqual([[2], false, 2, false]);
  });

  it("has no radio in a pane mounted without the page's context", () => {
    const { seen } = read(null);
    const { enabled, several, unheard } = seen().radios;
    expect([ids(enabled.value), several.value, unheard.value]).toEqual([[], false, null]);
  });

  it("are the topic a test's daemon tells, radio 1 alone unless the test tells its own", () => {
    expect(ids(read(fakeDaemon()).seen().radios.enabled.value)).toEqual([1]);
    const { seen } = read(fakeDaemon({ radios: BOTH }));
    expect([seen().radios.told.value, ids(seen().radios.enabled.value)]).toEqual([true, [1, 2]]);
  });

  it("are made once for the page: every pane reads the same radios", () => {
    const daemon = fakeDaemon({ radios: BOTH });
    expect(read(daemon).seen().radios).toBe(read(daemon).seen().radios);
    expect(read(daemon).seen().radios).not.toBe(read(fakeDaemon()).seen().radios);
  });

  it("keep each radio the same object over a patch of its counts, while its row follows; a changed radio is a new one", async () => {
    const one = radioRow(1, "kenwood-tnc2");
    const two = radioRow(2, "mercury");
    const daemon = fakeDaemon({ radios: topic(one, two) });
    const { all, byId } = read(daemon).seen().radios;
    const [first, second] = all.value;
    const list = all.value;
    await tell(daemon, { radios: topic(one, { ...two, stats: { ...two.stats, packets: 5 } }) });
    expect([all.value, all.value[0], all.value[1], byId(2)]).toEqual([list, first, second, second]);
    expect(all.value).toBe(list);
    expect(all.value[1]).toBe(second);
    expect(all.value[1]?.row.stats.packets).toBe(5);
    await tell(daemon, { radios: topic(one, { ...two, state: "waiting" }) });
    expect(all.value).not.toBe(list);
    expect(all.value[0]).toBe(first);
    expect(all.value[1]).not.toBe(second);
    expect(byId(2)?.connected).toBe(false);
  });

  it("names a radio where several are on, and always one that is not on", async () => {
    const daemon = fakeDaemon({
      radios: topic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury", { removed: true, enabled: false })),
    });
    const { named } = read(daemon).seen().radios;
    expect([named(1), named(2)]).toEqual([false, true]);
    await tell(daemon, { radios: topic(radioRow(1, "kenwood-tnc2"), radioRow(3, "kiss", { number: 2 })) });
    expect([named(1), named(3)]).toEqual([true, true]);
  });

  it("names, orders and labels the radios of the new types as every other, and offers to send on none that only receives (a LoRa board, the iGate's log, a text monitor)", () => {
    const daemon = fakeDaemon({
      radios: topic(
        radioRow(1, "kenwood-tnc2"),
        radioRow(2, "mercury"),
        radioRow(3, "lora-tcp", { position: 5 }),
        radioRow(4, "tnc-text", { number: 2, position: 3 }),
        radioRow(5, "lora-console", { number: 2, position: 4 }),
        radioRow(6, "dummy-lora", { number: 3, name: "Bike" }),
      ),
      status: status({ unheard_radio: 1 }),
    });
    const { all, enabled, senders, severalSenders, unheard, named } = read(daemon).seen().radios;
    expect(all.value.map((radio) => [radio.id, radio.kind, radio.name])).toEqual([
      [1, "fm", "FM"],
      [2, "hf", "Mercury"],
      [4, "fm", "FM 2"],
      [5, "lora", "LoRa 2"],
      [3, "lora", "LoRa"],
      [6, "lora", "Bike"],
    ]);
    expect(ids(enabled.value)).toEqual([1, 2, 4, 5, 3, 6]);
    expect([ids(senders.value), severalSenders.value, unheard.value?.id]).toEqual([[1, 2, 3, 6], true, 1]);
    expect(all.value.map((radio) => named(radio.id))).toEqual([true, true, true, true, true, true]);
    // A LoRa board carries WIDE1-1; the two that only receive carry none.
    expect(all.value.map((radio) => radio.carriesPath)).toEqual([true, false, false, false, true, true]);
  });

  it("gives the radio a station or a message goes on, any radio by its id, and for a call nothing is known of the radio the daemon names for a call no radio heard", () => {
    const daemon = fakeDaemon({
      radios: topic(
        radioRow(1, "kenwood-tnc2"),
        radioRow(2, "mercury"),
        radioRow(3, "kiss", { number: 2 }),
        radioRow(4, "kiss", { number: 3, removed: true, enabled: false }),
      ),
      status: status({ unheard_radio: 3 }),
    });
    const { forStation, forMessage, unheard } = read(daemon).seen().radios;
    expect(unheard.value?.id).toBe(3);
    const row = station("OH2RDG", { heard: heardBy([1, 3]), radio_now: 3 });
    expect([
      forStation(row)?.id,
      forStation(row, [message(5, { state: "sending", radio_now: 2 })])?.id,
      forStation(null)?.id,
      forStation({ ...row, radio_now: null }),
    ]).toEqual([3, 2, 3, null]);
    expect([
      forMessage(message(6, { state: "acked", radio_id: 4 }))?.removed,
      forMessage(message(7, { state: "sending", radio_now: 3 }))?.name,
      forMessage(message(8, { state: "acked" })),
    ]).toEqual([true, "FM 2", null]);
  });

  it("gives the email radio the status names, else the first radio on that can send and the gateways hear", async () => {
    const daemon = fakeDaemon({
      radios: topic(radioRow(1, "kenwood-tnc2", { removed: true, enabled: false }), radioRow(3, "kiss")),
      status: status({ email_radio: 3 }),
    });
    const { email } = read(daemon).seen().radios;
    expect(email.value?.id).toBe(3);
    await tell(daemon, { status: null });
    expect(email.value?.id).toBe(3);
  });

  it("gives the radio this page added once its row has come in the topic", async () => {
    const daemon = fakeDaemon({ radios: topic(radioRow(1, "kenwood-tnc2")) });
    const { added } = read(daemon).seen().radios;
    expect(added.value).toBeNull();
    await tell(daemon, { radioAdded: { type: "radio_added", id: 5 } });
    expect(added.value).toBeNull();
    await tell(daemon, { radios: topic(radioRow(1, "kenwood-tnc2"), radioRow(5, "mercury")) });
    expect([added.value?.id, added.value?.kind]).toEqual([5, "hf"]);
  });
});
