import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import TncPanel from "@/components/TncPanel.vue";
import { NOW, ago, tncState } from "@/test/fixtures";

describe("TncPanel", () => {
  it("counts the keep-alive's checks, probes and reopens", () => {
    const tnc = tncState();
    const text = mount(TncPanel, {
      props: { tnc: { ...tnc, stats: { ...tnc.stats, keepalive_checks: 3, watchdog_probes: 12, port_reopens: 2 } }, now: NOW },
    }).text();
    expect(text).toContain("3 checks, 12 probes, 2 reopens");
  });

  it("shows the state, the port, the speed, the counters and the lines", () => {
    const text = mount(TncPanel, { props: { tnc: tncState(), now: NOW } }).text();
    expect(text).toContain("connected");
    expect(text).toContain("/dev/brainbox_3");
    expect(text).toContain("9600 baud");
    expect(text).toContain("2.0 kB in");
    expect(text).toContain("12 received, 1 rejected");
    expect(text).toContain("30 s ago");
    expect(text).toContain("0 checks, 0 probes, 0 reopens");
    expect(text).toContain("Digipeated0");
    expect(text).toContain("NeoAPRS: opened /dev/brainbox_3");
  });

  it("says why it is not connected", () => {
    const wrapper = mount(TncPanel, {
      props: { tnc: tncState({ state: "waiting", problem: "no KISS frames on /dev/brainbox_3", last_error: "busy" }), now: NOW },
    });
    expect(wrapper.find(".statepill").classes()).toContain("tnc-waiting");
    expect(wrapper.find(".problem").text()).toBe("no KISS frames on /dev/brainbox_3");
    expect(wrapper.text()).toContain("busy");
  });

  it("says since when a silent radio has said nothing, in place of the daemon's line", () => {
    const wrapper = mount(TncPanel, {
      props: { tnc: tncState({ state: "silent", describe: "silent since 09:00 (7 min)", silent_since: ago(7 * 60) }), now: NOW },
    });
    expect(wrapper.find(".statepill").text()).toBe("silent");
    expect(wrapper.find(".statepill").classes()).toContain("tnc-silent");
    expect(wrapper.find(".toolbar").text()).toMatch(/nothing heard since \d\d:\d\d \(7 min\)/);
    expect(wrapper.find(".toolbar").text()).not.toContain("silent since 09:00");
  });

  it("asks for a reconnect", async () => {
    const wrapper = mount(TncPanel, { props: { tnc: tncState(), now: NOW } });
    await wrapper.find("button").trigger("click");
    expect(wrapper.emitted("reconnect")).toHaveLength(1);
  });

  it("has no beacon box: the beacon is a tab of its own", () => {
    expect(
      mount(TncPanel, { props: { tnc: tncState(), now: NOW } })
        .find(".beaconbox")
        .exists(),
    ).toBe(false);
  });

  it("says there is no word before the daemon has spoken", () => {
    expect(mount(TncPanel, { props: { tnc: null, now: NOW } }).text()).toContain("No word from the daemon yet.");
  });

  it("follows the end of the lines, unless they were scrolled up", async () => {
    const wrapper = mount(TncPanel, { props: { tnc: tncState(), now: NOW }, attachTo: document.body });
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
