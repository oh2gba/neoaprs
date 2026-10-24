import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import PanelFooter from "@/components/PanelFooter.vue";
import type { Connection } from "@/lib/hub";
import { fakeDaemon, withDaemon, type Given } from "@/test/context";
import { cssRule, mediaRule } from "@/test/css";
import { ago, NOW, status, tncState } from "@/test/fixtures";

const base = { connection: "open" as Connection, tnc: tncState(), version: "0.6.0", now: NOW };
type Parts = Pick<Given, "connection" | "tnc" | "version" | "now" | "status">;
const footer = (parts: Parts = {}) => mount(PanelFooter, { global: withDaemon(fakeDaemon({ ...base, ...parts })) });
const radio = (parts: Parts = {}) => footer(parts).find("button.status");
const connecting = (describe: string) => radio({ tnc: tncState({ state: "connecting", problem: "", describe }) });

describe("PanelFooter", () => {
  it("is one line with the version", () => {
    const wrapper = footer();
    expect(wrapper.html()).toMatch(/^<footer/);
    expect(wrapper.find(".version").text()).toBe("NeoAPRS 0.6.0");
    expect(wrapper.find(".version").classes()).toContain("muted");
    expect(wrapper.text()).toBe("NeoAPRS 0.6.0");
  });

  it("says nothing of the version before the daemon has said it", () => {
    expect(footer({ version: "" }).find(".version").exists()).toBe(false);
  });

  it("shows a newer version as a button that asks for the panel with the steps, the project's note as the title", async () => {
    const update = { version: "0.6.1", url: "https://oh2gba.github.io/neoaprs/", message: "Fixes the map download" };
    const wrapper = footer({ status: status({ update }) });
    const button = wrapper.find("button.update");
    expect(button.text()).toBe("Update to 0.6.1");
    expect(button.attributes("title")).toBe("Fixes the map download");
    expect(button.element.previousElementSibling).toBe(wrapper.find(".version").element);
    await button.trigger("click");
    expect(wrapper.emitted("update")).toHaveLength(1);
  });

  it("titles the button Update to the version when the project sent no note", () => {
    const update = { version: "0.6.1", url: "", message: "" };
    expect(
      footer({ status: status({ update }) })
        .find("button.update")
        .attributes("title"),
    ).toBe("Update to 0.6.1");
  });

  it("shows the whole Update to 0.6.1 on a phone too: no style rule cuts it short", () => {
    expect(cssRule(".size-phone .update-to")).toBe("");
    expect(cssRule(".size-phone .update")).not.toMatch(/display:\s*none/);
    expect(cssRule(".size-phone .version")).not.toMatch(/display:\s*none/);
  });

  it("shows no button while there is no newer version", () => {
    expect(footer({ status: status() }).find(".update").exists()).toBe(false);
    expect(footer().find(".update").exists()).toBe(false);
  });

  it("says nothing of the radio while it is connected", () => {
    const wrapper = footer();
    expect(wrapper.find("button.status").exists()).toBe(false);
    expect(wrapper.text()).not.toMatch(/radio|daemon|connect/i);
  });

  it("says Radio: searching… in the warning colour while the TNC looks for the port, with its problem as the title", () => {
    const button = connecting("listening on /dev/brainbox_1 for the radio");
    expect(button.text()).toBe("Radio: searching…");
    expect(button.classes()).toContain("link-warn");
    expect(button.attributes("title")).toBe("listening on /dev/brainbox_1 for the radio");
  });

  it("says Radio: entering KISS… while the line is open and the TNC is put into KISS", () => {
    const button = connecting("/dev/brainbox_3 at 9600, entering KISS, 0 packets");
    expect(button.text()).toBe("Radio: entering KISS…");
    expect(button.classes()).toContain("link-warn");
  });

  it("says Radio: not connected while the TNC waits between two tries or is stopped, why as the title", () => {
    const waiting = radio({ tnc: tncState({ state: "waiting", problem: "no radio found on /dev/brainbox_*", describe: "waiting" }) });
    expect(waiting.text()).toBe("Radio: not connected");
    expect(waiting.classes()).toContain("link-warn");
    expect(waiting.attributes("title")).toBe("no radio found on /dev/brainbox_*");
    expect(radio({ tnc: tncState({ state: "stopped", problem: "" }) }).text()).toBe("Radio: not connected");
  });

  it("says Radio: waiting… before the TNC has said anything", () => {
    const button = radio({ tnc: null });
    expect(button.text()).toBe("Radio: waiting…");
    expect(button.classes()).toContain("link-warn");
  });

  it("says Radio: silent while the line is open and the radio does not answer, with since when and how long as the title", () => {
    const button = radio({ tnc: tncState({ state: "silent", problem: "", describe: "silent since 18:43 (300 min)", silent_since: ago(5 * 3600 + 120) }) });
    expect(button.text()).toBe("Radio: silent");
    expect(button.classes()).toContain("link-warn");
    expect(button.attributes("title")).toMatch(/^nothing heard since \d\d:\d\d \(5 h\)$/);
  });

  it("says Daemon offline in red while the socket is down, whatever the TNC was", () => {
    const button = radio({ connection: "closed" });
    expect(button.text()).toBe("Daemon offline");
    expect(button.classes()).toContain("link-bad");
    expect(cssRule(".link-bad")).toMatch(/color:\s*var\(--bad\)/);
  });

  it("says Connecting… while the socket is still being opened", () => {
    const button = radio({ connection: "connecting" });
    expect(button.text()).toBe("Connecting…");
    expect(button.classes()).toContain("link-warn");
    expect(cssRule(".link-warn")).toMatch(/color:\s*var\(--warn\)/);
  });

  it("has the radio message as a button that asks for the Settings tab, where the radio is", async () => {
    const wrapper = footer({ tnc: tncState({ state: "waiting", problem: "x" }) });
    expect(wrapper.find("[role='status'] button.status").text()).toBe("Radio: not connected");
    await wrapper.find("button.status").trigger("click");
    expect(wrapper.emitted("radio")).toHaveLength(1);
  });

  it("has no port, speed or packet count in its words: they are in the TNC group of the Settings tab", () => {
    const text = footer({ tnc: tncState({ state: "waiting", problem: "x", describe: "/dev/brainbox_3 at 9600, 4 packets" }) }).text();
    expect(text).not.toMatch(/brainbox|9600|packets/);
  });

  it("keeps the status region in place whether there is a message or not, so a screen reader hears it come", () => {
    expect(footer().find("[role='status']").exists()).toBe(true);
    expect(footer({ connection: "closed" }).find("[role='status']").exists()).toBe(true);
  });

  it("has the same markup around the message whether it is there or not: the line has the same elements, and a height of its own", () => {
    const fine = footer();
    const bad = footer({ tnc: tncState({ state: "waiting", problem: "x" }) });
    expect(fine.classes()).toEqual(bad.classes());
    expect(fine.find(".footradio").exists()).toBe(true);
    expect(bad.find(".footradio").exists()).toBe(true);
    expect(cssRule(".panelfoot")).toMatch(/(^|;)\s*height:\s*26px/);
    expect(cssRule(".panelfoot")).not.toMatch(/min-height|flex-wrap:\s*wrap/);
    expect(cssRule(".panelfoot")).toMatch(/flex:\s*none/);
    expect(mediaRule("(pointer: coarse)", ".panelfoot")).toMatch(/height:\s*36px/);
    expect(cssRule(".size-phone .panelfoot")).toMatch(/height:\s*calc\(28px \+ env\(safe-area-inset-bottom\)\)/);
  });

  it("does not show what the daemon costs the machine on the line: only the title of the version has it, with the uptime", () => {
    const wrapper = footer({ status: status({ cpu_percent: 0.3, rss_mb: 42.4, uptime_sec: 3 * 3600 }) });
    expect(wrapper.text()).not.toMatch(/MB|%/);
    expect(wrapper.find(".version").attributes("title")).toBe("NeoAPRS uses 0.3 % of one processor core and 42 MB of memory, running for 3 h");
    expect(footer().find(".version").attributes("title")).toBeUndefined();
  });
});
