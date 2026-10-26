import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SettingsForm from "@/components/SettingsForm.vue";
import { fakeDaemon, tell, withDaemon, type Given } from "@/test/context";
import { configValues, igateState } from "@/test/fixtures";

function make(extra: Record<string, string> = {}, more: Given = {}) {
  const daemon = fakeDaemon({ config: configValues(extra), ...more });
  const wrapper = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(daemon) });
  const group = () => wrapper.findAll("fieldset").find((f) => f.find("legend").text() === "Internet");
  return { wrapper, daemon, group };
}

describe("the Internet group of the Settings tab", () => {
  it("is after the TNC group and has one switch, Receive only, with its (i), and while it is on the status line: no passcode, no link, no server, no note", () => {
    const { wrapper, group } = make({ "igate/enabled": "true", "igate/password": "19628" }, { igate: igateState() });
    const legends = wrapper.findAll("form > fieldset").map((f) => f.find("legend").text());
    expect(legends.slice(0, 2)).toEqual(["Radio", "Internet"]);
    const box = group();
    expect(box?.findAll(".field").map((f) => f.find("label").text())).toEqual(["Receive only"]);
    expect(box?.findAll("input")).toHaveLength(1);
    expect(box?.find(".infotip").exists()).toBe(true);
    for (const gone of ["#set-igate-server", "#set-igate-password", "a.btn", ".igate-note", ".igate-request"])
      expect(box?.find(gone).exists(), gone).toBe(false);
    expect(box?.find(".statetext").exists()).toBe(false);
    expect(box?.find(".tag").exists()).toBe(false);
    expect(box?.find(".tncstatus").text()).toBe("Connected, receiving");
    expect(box?.text()).not.toMatch(/gate|passcode|iGate/i);
  });

  it("says in its (i), in one line, what it shows and that nothing is sent", async () => {
    const { group } = make();
    await group()?.find(".info-toggle").trigger("click");
    expect(
      group()
        ?.findAll(".info-line")
        .map((l) => l.text()),
    ).toEqual(["Shows stations from APRS-IS within the map's radius. Nothing is sent."]);
  });

  it("shows only the switch while it is off, and the status line the moment it is on", async () => {
    const { group } = make({ "igate/enabled": "false" }, { igate: igateState({ state: "off", enabled: false }) });
    expect(
      group()
        ?.findAll(".field")
        .map((f) => f.find("label").text()),
    ).toEqual(["Receive only"]);
    for (const gone of [".tncstatus"]) expect(group()?.find(gone).exists(), gone).toBe(false);
    await group()?.find("#set-igate-enabled").setValue(true);
    expect(group()?.find(".tncstatus").exists()).toBe(true);
    await group()?.find("#set-igate-enabled").setValue(false);
    expect(group()?.find(".tncstatus").exists()).toBe(false);
  });

  it("says Connecting to the server while it connects, and why it is not connected", () => {
    expect(
      make({ "igate/enabled": "true" }, { igate: igateState({ state: "connecting", server: "T2FINLAND" }) })
        .group()
        ?.find(".tncstatus")
        .text(),
    ).toBe("Connecting to T2FINLAND…");
    expect(
      make({ "igate/enabled": "true" }, { igate: igateState({ state: "connecting", problem: "Connection refused" }) })
        .group()
        ?.find(".tncstatus")
        .text(),
    ).toBe("Not connected: Connection refused");
  });

  it("says Set your call first, and shows no field, while the call is not set", () => {
    const { group } = make({ "station/call": "" }, { igate: igateState({ state: "connecting" }) });
    expect(group()?.text()).toContain("Set your call first");
    expect(group()?.findAll(".field")).toHaveLength(0);
    expect(group()?.find(".tncstatus").exists()).toBe(false);
  });

  it("shows the switch as soon as the call is set", async () => {
    const { daemon, group } = make({ "station/call": "" });
    expect(group()?.findAll(".field")).toHaveLength(0);
    await tell(daemon, { config: configValues({ "station/call": "OH2GBA" }) });
    expect(group()?.findAll(".field")).toHaveLength(1);
  });

  it("sends the switch as it is changed", async () => {
    const { group, daemon } = make();
    await group()?.find("#set-igate-enabled").setValue(true);
    expect(daemon.send).toHaveBeenCalledWith({ cmd: "set_config", values: { "igate/enabled": "true" } });
  });
});
