import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SettingsForm from "@/components/SettingsForm.vue";
import { fakeDaemon, tell, withDaemon, type Given } from "@/test/context";
import { configValues, igateState } from "@/test/fixtures";

function make(extra: Record<string, string> = {}, more: Given = {}) {
  const daemon = fakeDaemon({ config: configValues(extra), ...more });
  const wrapper = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(daemon) });
  const group = () => wrapper.findAll("fieldset").find((f) => f.find("legend").text() === "iGate");
  return { wrapper, daemon, group };
}

describe("the iGate group of the Settings tab", () => {
  it("is after the TNC group and has the switch, the passcode with its link, the status line and the quiet line, and no server", () => {
    const { wrapper, group } = make({ "igate/enabled": "true", "igate/password": "19628" }, { igate: igateState() });
    const legends = wrapper.findAll("form > fieldset").map((f) => f.find("legend").text());
    expect(legends.slice(0, 2)).toEqual(["TNC", "iGate"]);
    const box = group();
    expect(box?.findAll(".field").map((f) => f.find("label").text())).toEqual(["Gate to APRS-IS", "Passcode"]);
    expect(box?.find("#set-igate-server").exists()).toBe(false);
    expect(box?.find(".statepill").text()).toBe("connected");
    expect(box?.find(".tncstatus").text()).toBe("Connected to T2FINLAND, 1234 packets gated, last 12 s ago");
    expect(box?.find(".tncstatus").attributes("title")).toBe("Not gated: already via the internet: 31, duplicate: 6, query: 3");
    expect(box?.find(".igate-note").text()).toBe("Receive only: what the radio hears goes to APRS-IS; nothing from the internet is sent on the air.");
  });

  it("has a password field, which shows dots and is not offered to a password manager", () => {
    const { group } = make({ "igate/password": "19628" });
    const input = group()?.find("#set-igate-password");
    expect(input?.attributes("type")).toBe("password");
    expect(input?.attributes("autocomplete")).toBe("new-password");
    expect((input?.element as HTMLInputElement).value).toBe("19628");
  });

  it("has a link next to the passcode that opens the request page in a new tab, with our call", () => {
    const { group } = make({ "station/call": "OH2GBA-10" });
    const link = group()?.find("a.igate-request");
    expect(link?.text()).toBe("Request a passcode");
    expect(link?.attributes("href")).toBe("https://oh2gba.eu/neoaprs/passcode?call=OH2GBA");
    expect(link?.attributes("target")).toBe("_blank");
    expect(link?.attributes("rel")).toContain("noopener");
  });

  it("says in one line what the passcode is for", () => {
    const { group } = make();
    expect(group()?.find(".info-line").exists()).toBe(false);
    expect(group()?.text()).not.toContain("comes by e-mail");
  });

  it("says Set your call first, and shows no field, while the call is not set", () => {
    const { group } = make({ "station/call": "" }, { igate: igateState({ state: "connecting" }) });
    expect(group()?.text()).toContain("Set your call first");
    expect(group()?.findAll(".field")).toHaveLength(0);
    expect(group()?.find(".statepill").exists()).toBe(false);
  });

  it("shows the fields as soon as the call is set", async () => {
    const { daemon, group } = make({ "station/call": "" });
    expect(group()?.findAll(".field")).toHaveLength(0);
    await tell(daemon, { config: configValues({ "station/call": "OH2GBA" }) });
    expect(group()?.findAll(".field")).toHaveLength(2);
  });

  it("sends the switch as it is changed", async () => {
    const { group, daemon } = make({ "igate/password": "" });
    await group()?.find("#set-igate-enabled").setValue(true);
    expect(daemon.send).toHaveBeenCalledWith({ cmd: "set_config", values: { "igate/enabled": "true" } });
  });

  it("sends the passcode when it is typed and Enter is pressed", async () => {
    const { group, daemon } = make({ "igate/password": "" });
    const input = group()?.find("#set-igate-password");
    await input?.setValue("19628");
    await input?.trigger("keydown.enter");
    expect(daemon.send).toHaveBeenCalledWith({ cmd: "set_config", values: { "igate/password": "19628" } });
  });
});
