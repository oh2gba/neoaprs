import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import RadioStatus from "@/components/RadioStatus.vue";
import { clockText } from "@/lib/format";
import { NOW, ago, tncState } from "@/test/fixtures";

const radio = (tnc: ReturnType<typeof tncState> | null) => mount(RadioStatus, { props: { tnc, now: NOW } });

describe("RadioStatus", () => {
  it("has the state, one plain line, Reconnect and a closed Terminal, and none of the counters", () => {
    const wrapper = radio(tncState());
    expect(wrapper.find(".statepill").text()).toBe("connected");
    expect(wrapper.find(".tncstatus").text()).toBe("Connected to /dev/brainbox_3, last packet 30 s ago");
    expect(wrapper.find(".tncstatus").attributes("title")).toBe("11 packets heard, 2.0 kB in, 0 B out, 0 digipeated");
    expect(wrapper.find("button").text()).toBe("Reconnect");
    expect(wrapper.find<HTMLDetailsElement>("details").element.open).toBe(false);
    expect(wrapper.find("summary").text()).toBe("Terminal");
    for (const word of ["Opened", "Bytes", "Frames", "Keep-alive", "Speed", "Last error", "Details"]) expect(wrapper.text()).not.toContain(word);
  });

  it("says why it is not connected in the line, once", () => {
    const wrapper = radio(tncState({ state: "waiting", problem: "no KISS frames on /dev/brainbox_3", last_error: "busy" }));
    expect(wrapper.find(".statepill").classes()).toContain("tnc-waiting");
    expect(wrapper.find(".tncstatus").text()).toBe("Not connected: no KISS frames on /dev/brainbox_3");
    expect(wrapper.find(".problem").exists()).toBe(false);
  });

  it("has the problem of a line that is open as a line of its own", () => {
    const wrapper = radio(tncState({ problem: "no KISS frames on /dev/brainbox_3" }));
    expect(wrapper.find(".tncstatus").text()).toContain("Connected to");
    expect(wrapper.find(".problem").text()).toBe("no KISS frames on /dev/brainbox_3");
  });

  it("says since when a silent radio has said nothing", () => {
    const wrapper = radio(tncState({ state: "silent", describe: "silent since 09:00 (7 min)", silent_since: ago(7 * 60) }));
    expect(wrapper.find(".statepill").text()).toBe("silent");
    expect(wrapper.find(".statepill").classes()).toContain("tnc-silent");
    expect(wrapper.find(".tncstatus").text()).toMatch(/^nothing heard since \d\d:\d\d \(7 min\)$/);
  });

  it("says it is searching and lists the ports behind a click", () => {
    const wrapper = radio(tncState({ state: "waiting", path: "", describe: "listening on /dev/ttyUSB0, /dev/ttyUSB1 for the radio" }));
    expect(wrapper.find(".tncstatus").text()).toBe("Searching for the radio…");
    const ports = wrapper.findAll("details").find((d) => d.find("summary").text() === "Ports");
    expect(ports?.element.open).toBe(false);
    expect(ports?.findAll("li").map((li) => li.text())).toEqual(["/dev/ttyUSB0", "/dev/ttyUSB1"]);
    expect(
      radio(tncState())
        .findAll("summary")
        .map((s) => s.text()),
    ).toEqual(["Terminal"]);
  });

  it("tells how many packets the digipeater repeated, while it is on", () => {
    const tnc = tncState({ stats: { ...tncState().stats, digipeated: 5 } });
    expect(radio(tnc).find(".tncstatus").text()).not.toContain("digipeated");
    expect(
      mount(RadioStatus, { props: { tnc, now: NOW, digipeater: true } })
        .find(".tncstatus")
        .text(),
    ).toMatch(/, digipeated 5$/);
  });

  it("asks for a reconnect", async () => {
    const wrapper = radio(tncState());
    await wrapper.find("button").trigger("click");
    expect(wrapper.emitted("reconnect")).toHaveLength(1);
  });

  it("shows the lines of the terminal with their time in the viewer's time", () => {
    const at = new Date(NOW - 20_000).toISOString();
    const wrapper = radio(tncState({ lines: [`${at.slice(11, 19)} NeoAPRS: opened /dev/brainbox_3`] }));
    expect(wrapper.find(".tnclines").text()).toBe(`${clockText(at)} NeoAPRS: opened /dev/brainbox_3`);
  });

  it("says nothing before the daemon has spoken", () => {
    expect(radio(null).find(".radiostatus").exists()).toBe(false);
  });

  it("follows the end of the lines, unless they were scrolled up", async () => {
    const wrapper = mount(RadioStatus, { props: { tnc: tncState(), now: NOW }, attachTo: document.body });
    const box = wrapper.find<HTMLElement>(".tnclines").element;
    Object.defineProperty(box, "scrollHeight", { value: 1000, configurable: true });
    Object.defineProperty(box, "clientHeight", { value: 100, configurable: true });
    box.scrollTop = 900;
    await wrapper.setProps({ tnc: tncState({ lines: ["a", "b", "c"] }) });
    await wrapper.vm.$nextTick();
    expect(box.scrollTop).toBe(1000);
    box.scrollTop = 100;
    await wrapper.setProps({ tnc: tncState({ lines: ["a", "b", "c", "d"] }) });
    await wrapper.vm.$nextTick();
    expect(box.scrollTop).toBe(100);
    wrapper.unmount();
  });
});
