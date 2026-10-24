import "@/test/mockmap";
import { describe, expect, it, vi } from "vitest";
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
    expect(group.find("legend").text()).toBe("TNC");
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
    expect(wrapper.find(".toast").text()).toContain("messages/alert_command");
  });

  describe("settings that apply as they are changed", () => {
    const sets = (socket: FakeSocket) => socket.sent.filter((c) => (c as { cmd: string }).cmd === "set_config");
    const toast = (wrapper: VueWrapper) => wrapper.find(".toast.undo");
    const told = (socket: FakeSocket, changes: Record<string, string>) =>
      socket.say({ type: "state", topic: "config", rev: 1, value: configValues({ ...changes }) });

    it("has one queue for the Settings tab and the Beacon tab: the second change waits for the answer to the first", async () => {
      const { wrapper, socket } = await open();
      await wrapper.find("#pane-settings #set-digi-enabled").setValue(true);
      await wrapper.find("#pane-beacon #set-beacon-path").setValue("WIDE2-2");
      await wrapper.find("#pane-beacon #set-beacon-path").trigger("blur");
      expect(sets(socket)).toEqual([{ cmd: "set_config", values: { "digi/enabled": "true" } }]);
      told(socket, { "digi/enabled": "true" });
      await flushPromises();
      expect(sets(socket)).toHaveLength(2);
      expect(sets(socket)[1]).toEqual({ cmd: "set_config", values: { "beacon/path": "WIDE2-2" } });
    });

    it("offers Undo for the change that was made, and Undo sends the old values in one set_config", async () => {
      const { wrapper, socket } = await open();
      await wrapper.find("#pane-settings #set-digi-enabled").setValue(true);
      expect(toast(wrapper).exists()).toBe(false);
      told(socket, { "digi/enabled": "true" });
      await flushPromises();
      expect(toast(wrapper).text()).toContain("Digipeater changed");
      await toast(wrapper).find(".undo-button").trigger("click");
      expect(sets(socket)[1]).toEqual({ cmd: "set_config", values: { "digi/enabled": "false" } });
      expect(toast(wrapper).exists()).toBe(false);
      told(socket, {});
      await flushPromises();
      expect(toast(wrapper).exists()).toBe(false);
    });

    it("lets the toast go after ten seconds, and covers the latest of several quick changes", async () => {
      const { wrapper, socket } = await open();
      vi.useFakeTimers();
      await wrapper.find("#pane-settings #set-digi-enabled").setValue(true);
      told(socket, { "digi/enabled": "true" });
      await flushPromises();
      await wrapper.find("#pane-settings #set-map-radius_km").setValue("200");
      await wrapper.find("#pane-settings #set-map-radius_km").trigger("blur");
      expect(toast(wrapper).exists()).toBe(false);
      told(socket, { "digi/enabled": "true", "map/radius_km": "200" });
      await flushPromises();
      expect(toast(wrapper).text()).toContain("Map radius changed");
      vi.advanceTimersByTime(10001);
      await flushPromises();
      expect(toast(wrapper).exists()).toBe(false);
      vi.useRealTimers();
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
    const button = () => wrapper.find("#pane-settings .mapfetch-actions button.primary");
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

  it("opens the steps of the update for the way this copy was installed from the new version under the panel, and closes them when it is gone", async () => {
    const { wrapper, socket } = await open();
    expect(wrapper.find(".updatedialog").exists()).toBe(false);
    socket.say(hello({ install: { kind: "uv-tool", appimage: "", service: true, arch: "" } }));
    socket.say(status({ update: { version: "0.4.0", url: "", message: "" } }));
    await flushPromises();
    await wrapper.find("button.update").trigger("click");
    const panel = wrapper.find(".updatedialog");
    expect(panel.find("h2").text()).toBe("NeoAPRS 0.4.0 is available");
    expect(panel.find("code").text()).toContain("install.sh | sh");
    socket.say(status());
    await flushPromises();
    expect(wrapper.find(".updatedialog").exists()).toBe(false);
  });

  it("asks the daemon to check at once from the Settings tab and opens the steps from the answer", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Settings")?.trigger("click");
    const button = wrapper.findAll("#pane-settings button").find((b) => b.text() === "Check now");
    await button?.trigger("click");
    expect(socket.sent.filter((c) => (c as { cmd: string }).cmd === "update_check")).toHaveLength(1);
    socket.say({ type: "update_result", outcome: "newer", version: "0.4.0", text: "" });
    socket.say(status({ update: { version: "0.4.0", url: "", message: "" } }));
    await flushPromises();
    expect(wrapper.find("button.update").text()).toBe("Update to 0.4.0");
    await wrapper.find("#pane-settings button.updatecheck-result").trigger("click");
    expect(wrapper.find(".updatedialog h2").text()).toBe("NeoAPRS 0.4.0 is available");
  });
});
