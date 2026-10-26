import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SettingsForm from "@/components/SettingsForm.vue";
import { fakeDaemon, withDaemon, type Given } from "@/test/context";
import { ago, configValues, status, tncState } from "@/test/fixtures";

function make(extra: Record<string, string> = {}, more: Given = {}) {
  const daemon = fakeDaemon({ config: configValues(extra), ...more });
  const wrapper = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(daemon) });
  const group = () => wrapper.findAll("fieldset").find((f) => f.find("legend").text() === "Digipeater");
  return { wrapper, group };
}

const repeated = (n: number, at: string | null, held = 0) =>
  tncState({ stats: { ...tncState().stats, digipeated: n, digipeated_at: at, digipeat_held: held } });

describe("the status row of the Digipeater group", () => {
  it("is not there while the tickbox Enable is off", () => {
    expect(
      make({ "digi/enabled": "false" }, { tnc: repeated(3, ago(60)) })
        .group()
        ?.find(".statusfold")
        .exists(),
    ).toBe(false);
  });

  it("is the radio's row under the tickbox: on, and how many packets it repeated and when the last went", () => {
    const { group } = make({ "digi/enabled": "true" }, { tnc: repeated(12, ago(180)), status: status() });
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
    const { group } = make({ "digi/enabled": "true" }, { tnc: repeated(0, null, 2), status: status() });
    expect(group()?.find(".tncstatus").text()).toBe("None repeated yet");
    expect(
      group()
        ?.findAll(".igatefold")
        .map((p) => p.text())[1],
    ).toBe("2 frames held back: too many in a burst");
  });

  it("says off in the warn colour while RX only is ticked", () => {
    const { group } = make({ "digi/enabled": "true", "station/transmit": "false" }, { tnc: repeated(5, ago(60)) });
    expect(group()?.find(".statetext").text()).toBe("off");
    expect(group()?.find(".statetext").classes()).toContain("tnc-waiting");
    expect(group()?.find(".tncstatus").text()).toBe("RX only: nothing is repeated");
  });
});
