import "@/test/mockmap";
import { describe, expect, it } from "vitest";
import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { type FakeSocket } from "@/test/fakesocket";
import { openedAt } from "@/test/fakealert";
import { configValues, errorOf, fmRow, hello, mapState, radiosValue, status } from "@/test/fixtures";
import { open, tabButton, useAppHarness } from "@/test/app";
import { shown } from "@/test/shown";

useAppHarness();

describe("App: the Settings tab", () => {
  it("shows the radio link at the top of the TNC group of the Settings tab, with no Reconnect: the radio is found again by itself", async () => {
    const { wrapper, socket } = await open();
    expect(tabButton(wrapper, "TNC")).toBeUndefined();
    await tabButton(wrapper, "Settings")?.trigger("click");
    const group = wrapper.find("#pane-settings fieldset");
    expect(group.find("legend").text()).toBe("Radio");
    expect(group.find(".radiostatus .tncstatus").text()).toMatch(/^Last packet /);
    expect(group.find(".radiostatus summary button").exists()).toBe(false);
    expect(socket.sent.filter((c) => (c as { cmd: string }).cmd.includes("reconnect"))).toEqual([]);
  });

  it("opens the Settings tab, where the radio is, from the Radio mark of the header", async () => {
    const { wrapper, socket } = await open();
    socket.say({
      type: "state",
      topic: "radios",
      rev: 1,
      value: radiosValue(fmRow({ state: "connecting", problem: { code: "radio.searching", params: {} } })),
    });
    await flushPromises();
    await tabButton(wrapper, "Stations")?.trigger("click");
    await wrapper.find(".appheader .pill-radio").trigger("click");
    expect(wrapper.find("[aria-selected='true']").text()).toContain("Settings");
  });

  it("has the map's radius on the Settings tab and the station and beacon keys on the My station tab, none twice", async () => {
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
    socket.say(
      errorOf("set_config: messages/alert_command: 1001 characters is more than the 1000 allowed", "setting.too_long", {
        length: 1001,
        max: 1000,
      }),
    );
    await flushPromises();
    expect(wrapper.find("#set-messages-alert_command").element.closest(".field")?.textContent).toContain(
      "more than the 1000 allowed",
    );
    expect(wrapper.find<HTMLInputElement>("#set-messages-alert_command").element.value).toBe("x".repeat(1001));
    expect(wrapper.find(".toast").exists()).toBe(false);
  });

  describe("settings that apply as they are changed", () => {
    const sets = (socket: FakeSocket) => socket.sent.filter((c) => (c as { cmd: string }).cmd === "set_config");
    const toast = (wrapper: VueWrapper) => wrapper.find(".toast");
    /**
     * The daemon sends the settings again with these changes, a radio's own among the radios'
     * values.
     */
    const told = (socket: FakeSocket, changes: Record<string, string>) => {
      const own = (radio: boolean) =>
        Object.fromEntries(Object.entries(changes).filter(([key]) => key.startsWith("radio/") === radio));
      socket.say({ type: "state", topic: "config", rev: 1, value: configValues(own(false), own(true)) });
    };

    it("has one queue for the Settings tab and the My station tab: the second change waits for the answer to the first", async () => {
      const { wrapper, socket } = await open();
      await wrapper.find("#pane-settings #set-radio-1-digipeat").setValue(true);
      await wrapper.find("#pane-beacon #set-radio-1-path").setValue("custom");
      await wrapper.find("#pane-beacon #set-radio-1-path-typed").setValue("WIDE2-2");
      await wrapper.find("#pane-beacon #set-radio-1-path-typed").trigger("blur");
      expect(sets(socket)).toEqual([{ cmd: "set_config", values: { "radio/1/digipeat": "true" } }]);
      told(socket, { "radio/1/digipeat": "true" });
      await flushPromises();
      expect(sets(socket)).toHaveLength(2);
      expect(sets(socket)[1]).toEqual({ cmd: "set_config", values: { "radio/1/path": "WIDE2-2" } });
    });

    it("shows no toast when a change is saved, and none for the refusal of one: the refusal is under its field", async () => {
      const { wrapper, socket } = await open();
      await wrapper.find("#pane-settings #set-radio-1-digipeat").setValue(true);
      told(socket, { "radio/1/digipeat": "true" });
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
    expect(shown(button())).toBe("Checking size…");
    socket.say({
      type: "patch",
      topic: "map",
      rev: 1,
      ops: [
        {
          op: "replace",
          value: mapState({
            estimate: {
              bytes: 493_000_000,
              tiles: 41233,
              radius_km: 150,
              maxzoom: 12,
              box: [22.1, 58.8, 27.8, 61.5],
              build: "20261022",
            },
          }),
        },
      ],
    });
    await flushPromises();
    expect(shown(button())).toBe("Download 493 MB?");
    await button().trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "map_fetch" });
    socket.say({
      type: "patch",
      topic: "map",
      rev: 2,
      ops: [{ op: "replace", value: mapState({ state: "downloading", step: "world", percent: 42, blocked: "busy" }) }],
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
    await wrapper.find("#pane-settings .updateline button.btn").trigger("click");
    const panel = wrapper.find(".updatedialog");
    expect(panel.find("h2").text()).toBe("NeoAPRS 0.4.0 is available");
    // A copy installed from the wheel is sent to the release page.
    expect(panel.find("a[href$='/releases/tag/v0.4.0']").exists()).toBe(true);
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
    expect(wrapper.find("#pane-settings .updateline button.btn").text()).toBe("Update");
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

describe("App: the units", () => {
  const unitsBox = (wrapper: VueWrapper) => wrapper.find<HTMLInputElement>("#pane-settings #set-units-non_metric");

  it("has Non-metric units right under Language, above every group, and not on the My station tab", async () => {
    const { wrapper } = await open();
    await tabButton(wrapper, "Settings")?.trigger("click");
    const rows = [...(wrapper.find("#pane-settings form.settings").element.children as HTMLCollectionOf<HTMLElement>)];
    const language = rows.findIndex((row) => row.querySelector("#language") !== null);
    expect(rows[language + 1]?.querySelector("#set-units-non_metric")).not.toBeNull();
    expect(rows[language + 1]?.querySelector("label")?.textContent).toBe("Non-metric units");
    expect(wrapper.find("#pane-settings fieldset #set-units-non_metric").exists()).toBe(false);
    expect(wrapper.find("#pane-beacon #set-units-non_metric").exists()).toBe(false);
    expect(unitsBox(wrapper).element.checked).toBe(false);
  });

  it("sends the tick to the daemon, and the page turns to miles when the daemon tells it, with no reload", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Settings")?.trigger("click");
    await unitsBox(wrapper).setValue(true);
    expect(socket.sent).toContainEqual({ cmd: "set_config", values: { "units/non_metric": "true" } });
    await tabButton(wrapper, "Stations")?.trigger("click");
    const head = () => wrapper.findAll("#pane-stations th button").map((b) => b.text());
    expect(head().some((text) => text.startsWith("km"))).toBe(true);
    socket.say({ type: "state", topic: "config", rev: 1, value: configValues({ "units/non_metric": "true" }) });
    await flushPromises();
    expect(head().some((text) => text.startsWith("mi"))).toBe(true);
    socket.say({ type: "state", topic: "config", rev: 2, value: configValues() });
    await flushPromises();
    expect(head().some((text) => text.startsWith("km"))).toBe(true);
  });
});
