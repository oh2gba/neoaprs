import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import AppHeader from "@/components/AppHeader.vue";
import type { Connection } from "@/lib/hub";
import { cssRule } from "@/test/css";
import { ago, NOW, status, tncState } from "@/test/fixtures";

const base = { call: "OH2GBA", connection: "open" as Connection, tnc: tncState(), version: "0.1.0", unread: 0, now: NOW };
const header = (props: Partial<InstanceType<typeof AppHeader>["$props"]> = {}) => mount(AppHeader, { props: { ...base, ...props } });

describe("AppHeader", () => {
  it("shows the number of messages not seen next to the call, and a click asks for them", async () => {
    const wrapper = header({ unread: 2 });
    const mail = wrapper.find(".headmail");
    expect(mail.text()).toContain("2");
    expect(mail.attributes("title")).toContain("2 messages not seen yet");
    expect(wrapper.find(".call").element.nextElementSibling).toBe(mail.element);
    await mail.trigger("click");
    expect(wrapper.emitted("messages")).toHaveLength(1);
  });

  it('shows an amber button "no call set" in place of the call while the call is empty, and a click asks for the setup guide', async () => {
    const wrapper = header({ call: "" });
    expect(wrapper.find(".call").exists()).toBe(false);
    const button = wrapper.find(".nocall");
    expect(button.text()).toBe("no call set");
    await button.trigger("click");
    expect(wrapper.emitted("setup")).toHaveLength(1);
    expect(header().find(".nocall").exists()).toBe(false);
    expect(header({ call: null }).find(".nocall").exists()).toBe(false);
  });

  it("shows a newer version after the version as a button that asks for the panel with the steps, the project's note as the title", async () => {
    const update = { version: "0.2.0", url: "https://oh2gba.github.io/neoaprs/", message: "Fixes the map download" };
    const wrapper = header({ status: status({ update }) });
    const button = wrapper.find("button.update");
    expect(button.text()).toBe("Update to 0.2.0");
    expect(button.attributes("title")).toBe("Fixes the map download");
    await button.trigger("click");
    expect(wrapper.emitted("update")).toHaveLength(1);
  });

  it("titles the button Update to the version when the project sent no note", () => {
    const update = { version: "0.2.0", url: "", message: "" };
    expect(
      header({ status: status({ update }) })
        .find("button.update")
        .attributes("title"),
    ).toBe("Update to 0.2.0");
  });

  it("shows no button while there is no newer version", () => {
    expect(header({ status: status() }).find(".update").exists()).toBe(false);
    expect(header().find(".update").exists()).toBe(false);
  });

  it("shows nothing when all are seen", () => {
    expect(header().find(".headmail").exists()).toBe(false);
  });

  it("has the radio state as a button that asks for the Settings tab, where the radio is", async () => {
    const wrapper = header();
    expect(wrapper.find("[role='status'] button.status").text()).toBe("radio ok");
    await wrapper.find("button.status").trigger("click");
    expect(wrapper.emitted("radio")).toHaveLength(1);
  });

  it("is one dot and its words: green radio ok while the socket is open and the TNC is connected", () => {
    const wrapper = header();
    expect(wrapper.findAll(".dot")).toHaveLength(1);
    expect(wrapper.find(".status").text()).toBe("radio ok");
    expect(wrapper.find(".status").classes()).toContain("link-ok");
  });

  it("is amber with the TNC's state in a word and its problem as the title while the socket is up and the TNC is not connected", () => {
    const wrapper = header({ tnc: tncState({ state: "waiting", problem: "no radio found on /dev/brainbox_*", describe: "waiting" }) });
    expect(wrapper.find(".status").text()).toBe("radio: waiting");
    expect(wrapper.find(".status").classes()).toContain("link-warn");
    expect(wrapper.find(".status").attributes("title")).toBe("no radio found on /dev/brainbox_*");
    const connecting = (describe: string) => header({ tnc: tncState({ state: "connecting", problem: "", describe }) }).find(".status");
    expect(connecting("listening on /dev/brainbox_1 for the radio").text()).toBe("radio: searching");
    expect(connecting("/dev/brainbox_3 at 9600, entering KISS, 0 packets").text()).toBe("radio: entering KISS");
    expect(connecting("/dev/brainbox_3 at 9600, entering KISS, 0 packets").attributes("title")).toBe("/dev/brainbox_3 at 9600, entering KISS, 0 packets");
    expect(
      header({ tnc: tncState({ state: "stopped", problem: "" }) })
        .find(".status")
        .text(),
    ).toBe("radio: stopped");
    expect(header({ tnc: null }).find(".status").text()).toBe("radio: waiting");
  });

  it("is amber radio: silent while the line is open and the radio does not answer, with since when and how long as the title", () => {
    const wrapper = header({ tnc: tncState({ state: "silent", problem: "", describe: "silent since 18:43 (300 min)", silent_since: ago(5 * 3600 + 120) }) });
    expect(wrapper.find(".status").text()).toBe("radio: silent");
    expect(wrapper.find(".status").classes()).toContain("link-warn");
    expect(wrapper.find(".status").attributes("title")).toMatch(/^nothing heard since \d\d:\d\d \(5 h\)$/);
  });

  it("is red daemon offline while the socket is down, whatever the TNC was", () => {
    const wrapper = header({ connection: "closed" });
    expect(wrapper.find(".status").text()).toBe("daemon offline");
    expect(wrapper.find(".status").classes()).toContain("link-bad");
    expect(wrapper.find(".status").attributes("title")).toBeUndefined();
  });

  it("is amber while the socket is still being opened", () => {
    const wrapper = header({ connection: "connecting" });
    expect(wrapper.find(".status").text()).toBe("connecting...");
    expect(wrapper.find(".status").classes()).toContain("link-warn");
  });

  it("has no port, speed or packet count in it: they are on the TNC tab", () => {
    const text = header().text();
    expect(text).not.toMatch(/brainbox|9600|KISS|packets/);
    expect(header({ tnc: tncState({ state: "waiting", problem: "x" }) }).text()).not.toMatch(/brainbox|9600/);
  });

  it("does not show what the daemon costs the machine: only the title of the radio state has it, with the uptime", () => {
    expect(header().find(".process").exists()).toBe(false);
    expect(header().find("h1").attributes("title")).toBeUndefined();
    const wrapper = header({ status: status({ cpu_percent: 0.3, rss_mb: 42.4, uptime_sec: 3 * 3600 }) });
    expect(wrapper.text()).not.toMatch(/MB|%/);
    expect(wrapper.find(".status").text()).toBe("radio ok");
    expect(wrapper.find(".status").attributes("title")).toBe("NeoAPRS uses 0.3 % · 42 MB · up 3 h");
    const waiting = header({
      tnc: tncState({ state: "waiting", problem: "no radio found", describe: "waiting" }),
      status: status({ cpu_percent: 1, rss_mb: 50, uptime_sec: 60 }),
    });
    expect(waiting.find(".status").attributes("title")).toBe("no radio found\nNeoAPRS uses 1.0 % · 50 MB · up 1 min");
  });

  it("keeps a short Update button for a phone, where the version number is left out by the style sheet: the version is hidden there and the button is not", () => {
    const update = { version: "0.2.0", url: "", message: "" };
    const wrapper = header({ status: status({ update }) });
    expect(wrapper.find("button.update .update-to").text()).toBe("to 0.2.0");
    expect(cssRule(".size-phone .update-to")).toMatch(/display:\s*none/);
    expect(cssRule(".size-phone .version")).toMatch(/display:\s*none/);
    expect(cssRule(".size-phone .update")).not.toMatch(/display:\s*none/);
  });
});
