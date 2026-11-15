import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { defineComponent, h, shallowRef } from "vue";
import { useRadios, type Radios } from "@/composables/useRadios";
import { useFmOff, useRadiosNamed, useTwoRadios } from "@/composables/useRadiosOn";
import type { RadioRow } from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon, type FakeDaemon } from "@/test/context";
import { configValues, message, radioRow, radiosTopic as topic, station, status, tncState } from "@/test/fixtures";

/** What a pane reads of the radios: the one source and the views of before over it. */
function read(context: FakeDaemon | null) {
  let seen: { radios: Radios; two: boolean; fmOff: boolean; named: boolean } | undefined;
  const Reader = defineComponent({
    setup() {
      const radios = useRadios();
      const [two, fmOff, named] = [useTwoRadios(), useFmOff(), useRadiosNamed()];
      return () => {
        seen = { radios, two: two.value, fmOff: fmOff.value, named: named.value };
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

/** The views as useRadiosOn gave them before the topic `radios`, from the settings alone. */
function viewsBefore(values: Record<string, string>) {
  const fm = values["fm/enabled"] !== "false";
  const hf = values["hf/enabled"] === "true";
  return { two: fm && hf, fmOff: !fm, named: fm && hf }; // (named: more than one radio on, plan section 6)
}
const FM = { "fm/enabled": "true", "hf/enabled": "false" };
const BOTH = { "fm/enabled": "true", "hf/enabled": "true" };
const HF = { "fm/enabled": "false", "hf/enabled": "true" };

describe("useRadios", () => {
  it("reads the radios of the settings of before against a daemon that tells no topic `radios`", () => {
    const { seen } = read(fakeDaemon({ config: configValues(BOTH), radios: null, tnc: tncState({ state: "waiting" }) }));
    const { told, all, enabled, several, main, allowsPath, byId } = seen().radios;
    expect(all.value.map((radio) => [radio.id, radio.kind, radio.enabled, radio.row.type, radio.connected])).toEqual([
      [1, "fm", true, "kenwood-tnc2", false],
      [2, "hf", true, "mercury", false],
    ]);
    expect([told.value, ids(enabled.value), several.value, main.value?.id, allowsPath.value, byId(2)?.kind, byId(3)]).toEqual([
      false,
      [1, 2],
      true,
      1,
      true,
      "hf",
      undefined,
    ]);
  });

  it("reads the topic once it is told, follows it as it changes, and the main radio from the status", async () => {
    const daemon = fakeDaemon({ config: configValues(FM), radios: null });
    const { seen } = read(daemon);
    const { told, all, enabled, several, main, allowsPath, byId } = seen().radios;
    expect([told.value, ids(enabled.value), several.value]).toEqual([false, [1], false]);
    await tell(daemon, {
      radios: topic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury", { position: 0 })),
      status: status({ main_radio: 1 }),
      config: configValues(BOTH),
    });
    expect([told.value, ids(all.value), ids(enabled.value), several.value, main.value?.id, byId(2)?.row.type]).toEqual([
      true,
      [2, 1],
      [2, 1],
      true,
      1,
      "mercury",
    ]);
    await tell(daemon, {
      radios: topic(radioRow(1, "kenwood-tnc2", { enabled: false }), radioRow(2, "mercury")),
      status: status({ main_radio: 2 }),
      config: configValues(HF),
    });
    expect([ids(enabled.value), several.value, main.value?.id, allowsPath.value]).toEqual([[2], false, 2, false]);
  });

  it("is as a station with the FM radio alone in a pane mounted without the page's context", () => {
    const { seen } = read(null);
    const { enabled, several, main } = seen().radios;
    expect([ids(enabled.value), several.value, main.value?.id]).toEqual([[1], false, 1]);
  });

  it("are the topic a test's daemon tells for its settings, unless the test tells its own", () => {
    const { seen } = read(fakeDaemon({ config: configValues(BOTH) }));
    expect([seen().radios.told.value, ids(seen().radios.enabled.value)]).toEqual([true, [1, 2]]);
  });

  it("are made once for the page: every pane reads the same radios", () => {
    const daemon = fakeDaemon({ config: configValues(BOTH) });
    expect(read(daemon).seen().radios).toBe(read(daemon).seen().radios);
    expect(read(daemon).seen().radios).not.toBe(read(fakeDaemon()).seen().radios);
  });

  it("keep each radio the same object over a patch of its counts, while its row follows; a changed radio is a new one", async () => {
    const one = radioRow(1, "kenwood-tnc2");
    const two = radioRow(2, "mercury");
    const daemon = fakeDaemon({ config: configValues(BOTH), radios: topic(one, two) });
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
      config: configValues(FM),
      radios: topic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury", { removed: true, enabled: false })),
    });
    const { named } = read(daemon).seen().radios;
    expect([named(1), named(2)]).toEqual([false, true]);
    await tell(daemon, { radios: topic(radioRow(1, "kenwood-tnc2"), radioRow(3, "kiss", { number: 2 })) });
    expect([named(1), named(3)]).toEqual([true, true]);
  });

  it("gives the radio a station or a message goes on, any radio by its id, and the main radio for a call nothing is known of", () => {
    const daemon = fakeDaemon({
      config: configValues(BOTH),
      radios: topic(
        radioRow(1, "kenwood-tnc2"),
        radioRow(2, "mercury"),
        radioRow(3, "kiss", { number: 2 }),
        radioRow(4, "kiss", { number: 3, removed: true, enabled: false }),
      ),
      status: status({ main_radio: 3 }),
    });
    const { forStation, forMessage } = read(daemon).seen().radios;
    const row = station("OH2RDG", { heard_fm: 3, radio_now: 3 });
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

  it("gives the email radio the status names, else the first radio on that the gateways hear", async () => {
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
    const daemon = fakeDaemon({ config: configValues(FM), radios: topic(radioRow(1, "kenwood-tnc2")) });
    const { added } = read(daemon).seen().radios;
    expect(added.value).toBeNull();
    await tell(daemon, { radioAdded: { type: "radio_added", id: 5 } });
    expect(added.value).toBeNull();
    await tell(daemon, { radios: topic(radioRow(1, "kenwood-tnc2"), radioRow(5, "mercury")) });
    expect([added.value?.id, added.value?.kind]).toEqual([5, "hf"]);
  });
});

describe("the views of before over the radios", () => {
  it("give for one FM radio, for FM and HF, for HF alone and for a daemon of the wire of before what they gave before", () => {
    const told: [Record<string, string>, RadioRow[]][] = [
      [FM, [radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury", { enabled: false })]],
      [BOTH, [radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury")]],
      [HF, [radioRow(1, "kenwood-tnc2", { enabled: false }), radioRow(2, "mercury")]],
    ];
    for (const [values, rows] of told) {
      const label = JSON.stringify(values);
      const fromTopic = read(fakeDaemon({ config: configValues(values), radios: topic(...rows) })).seen();
      const fromSettings = read(fakeDaemon({ config: configValues(values), radios: null })).seen();
      expect({ two: fromTopic.two, fmOff: fromTopic.fmOff, named: fromTopic.named }, label).toEqual(viewsBefore(values));
      expect({ two: fromSettings.two, fmOff: fromSettings.fmOff, named: fromSettings.named }, label).toEqual(viewsBefore(values));
    }
    const alone = read(null).seen();
    expect([alone.two, alone.fmOff, alone.named]).toEqual([false, false, false]);
  });

  it("agree with the settings of before while the topic is a moment behind them, after a save and before the settings are told", async () => {
    const daemon = fakeDaemon({ config: configValues(BOTH), radios: topic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury")) });
    const { seen } = read(daemon);
    expect([seen().two, seen().fmOff]).toEqual([true, false]);
    await tell(daemon, { config: configValues(HF) });
    expect([seen().two, seen().fmOff, seen().named]).toEqual([false, true, false]);
    await tell(daemon, { config: null, radios: topic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury")) });
    expect([seen().two, seen().fmOff]).toEqual([false, false]);
  });

  it("are not broken by three radios or by a removed one: the old views do not show what they cannot name", () => {
    const three = read(
      fakeDaemon({ config: configValues(BOTH), radios: topic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury"), radioRow(3, "kiss", { number: 2 })) }),
    ).seen();
    expect([three.two, three.fmOff, ids(three.radios.enabled.value), three.radios.several.value]).toEqual([true, false, [1, 2, 3], true]);
    const fmAndFm = read(fakeDaemon({ config: configValues(FM), radios: topic(radioRow(1, "kenwood-tnc2"), radioRow(3, "kiss", { number: 2 })) })).seen();
    expect([fmAndFm.two, fmAndFm.fmOff, fmAndFm.radios.several.value]).toEqual([false, false, true]);
    const removed = read(
      fakeDaemon({ config: configValues(FM), radios: topic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury", { removed: true, enabled: false })) }),
    ).seen();
    expect([removed.two, removed.fmOff, ids(removed.radios.all.value), ids(removed.radios.enabled.value)]).toEqual([false, false, [1, 2], [1]]);
    const fmRemoved = read(
      fakeDaemon({
        config: configValues(HF),
        radios: topic(radioRow(1, "kenwood-tnc2", { removed: true, enabled: false }), radioRow(3, "kiss", { number: 1 })),
      }),
    ).seen();
    expect([fmRemoved.two, fmRemoved.fmOff, fmRemoved.radios.main.value?.id]).toEqual([false, true, 3]);
  });

  it("keep the radios named as the page's context says", async () => {
    const named = shallowRef(false);
    const daemon = fakeDaemon({ radiosNamed: named });
    const { seen } = read(daemon);
    expect(seen().named).toBe(false);
    named.value = true;
    await tell(daemon, {});
    expect(seen().named).toBe(true);
  });
});
