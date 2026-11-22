import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SettingsForm from "@/components/SettingsForm.vue";
import { fakeDaemon, tell, withDaemon, type Given } from "@/test/context";
import { ago, configValues, fmRow, lineStats, radioRow, radiosTopic, status } from "@/test/fixtures";
import type { PassStats } from "@/protocol/protocol";

function make(extra: Record<string, string> = {}, more: Given = {}) {
  const own = Object.fromEntries(Object.entries(extra).filter(([key]) => /^(radio|pair)\//.test(key)));
  const station = Object.fromEntries(Object.entries(extra).filter(([key]) => !/^(radio|pair)\//.test(key)));
  const daemon = fakeDaemon({ config: configValues(station, own), ...more });
  const wrapper = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(daemon) });
  const group = () => wrapper.findAll("fieldset").find((f) => f.find("legend").text() === "Digipeater");
  return { wrapper, group };
}

const repeated = (n: number, at: string | null, held = 0) =>
  radiosTopic(fmRow({ stats: lineStats({ digipeated: n, digipeated_at: at, digipeat_held: held }) }));

describe("the status row of the Digipeater group", () => {
  it("is not there while the tickbox Enable is off", () => {
    expect(
      make({ "radio/1/digipeat": "false" }, { radios: repeated(3, ago(60)) })
        .group()
        ?.find(".statusfold")
        .exists(),
    ).toBe(false);
  });

  it("is the radio's row under the tickbox: on, and how many packets it repeated and when the last went", () => {
    const { group } = make({ "radio/1/digipeat": "true" }, { radios: repeated(12, ago(180)), status: status() });
    const fold = group()?.find("details.statusfold");
    expect(
      group()
        ?.element.querySelector(".field")
        ?.compareDocumentPosition(fold?.element as Element),
    ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(fold?.find(".statetext").text()).toBe("on");
    expect(fold?.find(".statetext").classes()).toContain("tnc-connected");
    expect(fold?.find(".tncstatus").text()).toBe("12 packets repeated · last 3 min ago");
    expect(fold?.findAll(".igatefold").map((p) => p.text())).toEqual([expect.stringMatching(/^Counted since /)]);
  });

  it("says none repeated yet at 0, and says how many frames the burst limit held back", () => {
    const { group } = make({ "radio/1/digipeat": "true" }, { radios: repeated(0, null, 2), status: status() });
    expect(group()?.find(".tncstatus").text()).toBe("None repeated yet");
    expect(
      group()
        ?.findAll(".igatefold")
        .map((p) => p.text())[1],
    ).toBe("2 frames held back: too many in a burst");
  });

  it("says off in the warn colour while RX only is on", () => {
    const { group } = make(
      { "radio/1/digipeat": "true", "station/transmit": "false" },
      { radios: repeated(5, ago(60)) },
    );
    expect(group()?.find(".statetext").text()).toBe("off");
    expect(group()?.find(".statetext").classes()).toContain("tnc-waiting");
    expect(group()?.find(".tncstatus").text()).toBe("RX only: nothing is repeated");
  });
});

describe("the status row of a pair of radios", () => {
  const ON = { "pair/1/2/enabled": "true", "pair/1/2/ssid": "12" };
  const onto = (heard_on: number, extra: Partial<PassStats> = {}): PassStats[] => [
    { heard_on, sent: 0, sent_at: null, held: 0, too_long: 0, ...extra },
  ];
  /** Radio 1 (FM) and radio 2 (Mercury), with what the pair passed onto each. */
  const pairOf = (ontoFm: PassStats[], ontoHf: PassStats[]) =>
    radiosTopic(
      fmRow({ stats: lineStats({ passed: ontoFm }) }),
      radioRow(2, "mercury", { stats: lineStats({ passed: ontoHf }) }),
    );
  const row = (wrapper: ReturnType<typeof make>["wrapper"]) =>
    wrapper.find("#set-pair-1-2-ssid").element.closest("fieldset")?.querySelector(".statusfold");

  it("stands under the Call, says on and how many went both ways, and behind the arrow each way and what each radio held back or found too long", () => {
    const radios = pairOf(
      onto(2, { sent: 1, sent_at: ago(600) }),
      onto(1, { sent: 2, sent_at: ago(120), held: 3, too_long: 1 }),
    );
    const { wrapper } = make(ON, { radios, status: status() });
    expect(row(wrapper)?.querySelector(".statetext")?.textContent).toBe("on");
    expect(row(wrapper)?.querySelector(".tncstatus")?.textContent).toBe("3 packets repeated · last 2 min ago");
    expect([...(row(wrapper)?.querySelectorAll(".igatefold") ?? [])].map((p) => p.textContent)).toEqual([
      expect.stringMatching(/^Counted since /),
      "1 to FM radio · 2 to Mercury radio",
      "3 frames held back: too many for Mercury radio",
      "1 frame too long for Mercury radio",
    ]);
  });

  it("says none passed yet, and off while RX only is on", () => {
    expect(
      make(ON, { radios: pairOf([], []) })
        .wrapper.find("#set-pair-1-2-ssid")
        .element.closest("fieldset")
        ?.querySelector(".tncstatus")?.textContent,
    ).toBe("None repeated yet");
    const { wrapper } = make({ ...ON, "station/transmit": "false" }, { radios: pairOf([], []) });
    expect(row(wrapper)?.querySelector(".statetext")?.textContent).toBe("off");
    expect(row(wrapper)?.querySelector(".tncstatus")?.textContent).toBe("RX only: nothing is repeated");
  });

  it("keeps its one line when a count changes, and follows the topic radios after the page is drawn", async () => {
    const daemon = fakeDaemon({
      config: configValues({}, ON),
      radios: pairOf([], onto(1, { sent: 1, sent_at: ago(60) })),
      status: status(),
    });
    const wrapper = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(daemon) });
    const shape = () =>
      [...(row(wrapper)?.querySelectorAll("summary *, .statushead *") ?? [])].map((e) => e.tagName).join(" ");
    const before = shape();
    expect(row(wrapper)?.querySelector(".tncstatus")?.textContent).toMatch(/^1 packet repeated/);
    await tell(daemon, { radios: pairOf([], onto(1, { sent: 1234, sent_at: ago(5) })) });
    expect(row(wrapper)?.querySelector(".tncstatus")?.textContent).toMatch(/^1234 packets repeated/);
    expect(shape()).toBe(before);
  });
});
