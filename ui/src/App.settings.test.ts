import "@/test/mockmap";
import { describe, expect, it } from "vitest";
import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { type FakeSocket } from "@/test/fakesocket";
import { openedAt } from "@/test/fakealert";
import { configValues, errorOf, hello, mapState, status, tncState } from "@/test/fixtures";
import { open, tabButton, useAppHarness } from "@/test/app";

useAppHarness();

describe("App: the Settings tab", () => {
  it("shows the radio link at the top of the TNC group of the Settings tab and asks for a reconnect", async () => {
    const { wrapper, socket } = await open();
    expect(tabButton(wrapper, "TNC")).toBeUndefined();
    await tabButton(wrapper, "Settings")?.trigger("click");
    const group = wrapper.find("#pane-settings fieldset");
    expect(group.find("legend").text()).toBe("Radio");
    expect(group.find(".radiostatus .tncstatus").text()).toMatch(/^Last packet /);
    await group.find(".radiostatus button").trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "tnc_reconnect" });
  });

  it("opens the Settings tab, where the radio is, from the radio state under the panel", async () => {
    const { wrapper, socket } = await open();
    socket.say({
      type: "state",
      topic: "tnc",
      rev: 1,
      value: tncState({ state: "connecting", problem: "", describe: "listening on /dev/brainbox_1", searching: ["/dev/brainbox_1"] }),
    });
    await flushPromises();
    await tabButton(wrapper, "Stations")?.trigger("click");
    await wrapper.find(".panelfoot button.status").trigger("click");
    expect(wrapper.find("[aria-selected='true']").text()).toContain("Settings");
  });

  it("has the map's radius on the Settings tab and the station and beacon keys on the Beacon tab, none twice", async () => {
    const { wrapper, socket } = await open();
    socket.say({ type: "state", topic: "config", rev: 1, value: configValues() });
    await flushPromises();
    expect(wrapper.find("#pane-settings #set-map-radius_km").exists()).toBe(true);
    expect(wrapper.find("#pane-settings #set-map-hide_after_min").exists()).toBe(false);
    expect(wrapper.find("#pane-settings #set-station-call").exists()).toBe(false);
    expect(wrapper.find("#pane-beacon #set-station-call").exists()).toBe(true);
    expect(wrapper.find("#pane-beacon #set-map-radius_km").exists()).toBe(false);
  });

  it("changes the settings as they are made and shows the daemon's refusal under the field", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Settings")?.trigger("click");
    await wrapper.find("#set-messages-alert_command").setValue("x".repeat(1001));
    await wrapper.find("#set-messages-alert_command").trigger("blur");
    expect(socket.sent).toContainEqual({ cmd: "set_config", values: { "messages/alert_command": "x".repeat(1001) } });
    socket.say(errorOf("set_config: messages/alert_command: 1001 characters is more than the 1000 allowed", "setting.too_long", { length: 1001, max: 1000 }));
    await flushPromises();
    expect(wrapper.find("#set-messages-alert_command").element.closest(".field")?.textContent).toContain("more than the 1000 allowed");
    expect(wrapper.find<HTMLInputElement>("#set-messages-alert_command").element.value).toBe("x".repeat(1001));
    expect(wrapper.find(".toast").exists()).toBe(false);
  });

  describe("settings that apply as they are changed", () => {
    const sets = (socket: FakeSocket) => socket.sent.filter((c) => (c as { cmd: string }).cmd === "set_config");
    const toast = (wrapper: VueWrapper) => wrapper.find(".toast");
    const told = (socket: FakeSocket, changes: Record<string, string>) =>
      socket.say({ type: "state", topic: "config", rev: 1, value: configValues({ ...changes }) });

    it("has one queue for the Settings tab and the Beacon tab: the second change waits for the answer to the first", async () => {
      const { wrapper, socket } = await open();
      await wrapper.find("#pane-settings #set-digi-enabled").setValue(true);
      await wrapper.find("#pane-beacon #set-beacon-path").setValue("custom");
      await wrapper.find("#pane-beacon #set-beacon-path-typed").setValue("WIDE2-2");
      await wrapper.find("#pane-beacon #set-beacon-path-typed").trigger("blur");
      expect(sets(socket)).toEqual([{ cmd: "set_config", values: { "digi/enabled": "true" } }]);
      told(socket, { "digi/enabled": "true" });
      await flushPromises();
      expect(sets(socket)).toHaveLength(2);
      expect(sets(socket)[1]).toEqual({ cmd: "set_config", values: { "beacon/path": "WIDE2-2" } });
    });

    it("shows no toast when a change is saved, and none for the refusal of one: the refusal is under its field", async () => {
      const { wrapper, socket } = await open();
      await wrapper.find("#pane-settings #set-digi-enabled").setValue(true);
      told(socket, { "digi/enabled": "true" });
      await flushPromises();
      expect(toast(wrapper).exists()).toBe(false);
      expect(wrapper.find(".undo-button").exists()).toBe(false);
      await wrapper.find("#pane-settings #set-map-radius_km").setValue("200");
      await wrapper.find("#pane-settings #set-map-radius_km").trigger("blur");
      socket.say(errorOf("set_config: map/radius_km: 200 is too big", "setting.too_long", { length: 3, max: 2 }));
      await flushPromises();
      expect(toast(wrapper).exists()).toBe(false);
      expect(wrapper.find("#set-map-radius_km").element.closest(".field")?.textContent).toContain("2");
    });

    it("asks before the network is turned off on a page opened from another device", async () => {
      const { wrapper, socket } = await open();
      told(socket, { "web/network": "true", "web/key": "k7m2-x9pq-4hrt" });
      await flushPromises();
      openedAt("192.168.1.20");
      await wrapper.find("#pane-settings #set-web-network").setValue(false);
      expect(wrapper.find("#pane-settings .confirm-row").text()).toContain("This device will lose the page. Turn off?");
      expect(sets(socket)).toEqual([]);
    });
  });

  it("downloads the map from the Settings tab: the buttons send the commands and the progress follows the topic", async () => {
    const { wrapper, socket } = await open();
    socket.say({ type: "state", topic: "map", rev: 0, value: mapState() });
    await flushPromises();
    await tabButton(wrapper, "Settings")?.trigger("click");
    const button = () => wrapper.find("#pane-settings .mapfetch-button");
    await button().trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "map_estimate" });
    expect(socket.sent).not.toContainEqual({ cmd: "map_fetch" });
    expect(button().text()).toBe("Checking size…");
    socket.say({
      type: "patch",
      topic: "map",
      rev: 1,
      ops: [
        {
          op: "replace",
          value: mapState({ estimate: { bytes: 493_000_000, tiles: 41233, radius_km: 150, maxzoom: 12, box: [22.1, 58.8, 27.8, 61.5], build: "20261022" } }),
        },
      ],
    });
    await flushPromises();
    expect(button().text()).toBe("Download 493 MB?");
    await button().trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "map_fetch" });
    socket.say({
      type: "patch",
      topic: "map",
      rev: 2,
      ops: [{ op: "replace", value: mapState({ state: "downloading", step: "world", percent: 42, blocked: "a map job is running" }) }],
    });
    await flushPromises();
    expect(wrapper.find("#pane-settings .mapfetch-progress").text()).toBe("World map 42%");
  });

  it("opens the steps of the update for the way this copy was installed from the Update button of the row New version, and closes them when the new version is gone", async () => {
    const { wrapper, socket } = await open();
    expect(wrapper.find(".updatedialog").exists()).toBe(false);
    socket.say(hello({ install: { kind: "uv-tool", appimage: "", service: true, arch: "" } }));
    socket.say(status({ update: { version: "0.4.0", url: "", message: "" } }));
    await flushPromises();
    await tabButton(wrapper, "Settings")?.trigger("click");
    expect(wrapper.find("#pane-settings .updateline").text()).toContain("0.4.0 available");
    await wrapper.find("#pane-settings .updateline button").trigger("click");
    const panel = wrapper.find(".updatedialog");
    expect(panel.find("h2").text()).toBe("NeoAPRS 0.4.0 is available");
    expect(panel.find("code").text()).toContain("install.sh | sh");
    socket.say(status());
    await flushPromises();
    expect(wrapper.find(".updatedialog").exists()).toBe(false);
  });

  it("asks the daemon to check at once from the Settings tab and says the answer next to the button: checking, then the newer version with its Update button; no toast, nothing opens by itself", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Settings")?.trigger("click");
    const button = wrapper.findAll("#pane-settings button").find((b) => b.text() === "Check now");
    await button?.trigger("click");
    expect(socket.sent.filter((c) => (c as { cmd: string }).cmd === "update_check")).toHaveLength(1);
    expect(wrapper.find("#pane-settings .updateline").text()).toContain("checking…");
    socket.say({ type: "update_result", outcome: "newer", version: "0.4.0", text: "" });
    socket.say(status({ update: { version: "0.4.0", url: "", message: "" } }));
    await flushPromises();
    expect(wrapper.find("#pane-settings .updateline").text()).toContain("0.4.0 available");
    expect(wrapper.find("#pane-settings .updateline button").text()).toBe("Update");
    expect(wrapper.find(".updatedialog").exists()).toBe(false);
    expect(wrapper.find(".toast").exists()).toBe(false);
  });

  it("says up to date next to the button, in the ok colour and not in a toast, when the check finds the version up to date", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Settings")?.trigger("click");
    await wrapper
      .findAll("#pane-settings button")
      .find((b) => b.text() === "Check now")
      ?.trigger("click");
    socket.say({ type: "update_result", outcome: "current", version: "0.3.0", text: "" });
    await flushPromises();
    expect(wrapper.find("#pane-settings .updateline").text()).toMatch(/^NeoAPRS .*up to date$/);
    expect(wrapper.find("#pane-settings .updateline .statetext").classes()).toContain("update-current");
    expect(wrapper.find(".toast").exists()).toBe(false);
    expect(wrapper.find(".updatedialog").exists()).toBe(false);
  });
});
