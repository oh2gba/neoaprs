import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BeaconBox from "@/components/BeaconBox.vue";
import { NOW, ago, status } from "@/test/fixtures";

const inSeconds = (s: number): string => new Date(NOW + s * 1000).toISOString();

function box(extra = {}, connected = true, props: Record<string, unknown> = { statusOn: true }) {
  return mount(BeaconBox, {
    props: {
      status: status({ beacon_interval_min: 30, beacon_last_sent: ago(125), beacon_next_due: inSeconds(1700), ...extra }),
      connected,
      now: NOW,
      ...props,
    },
  });
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("BeaconBox", () => {
  it("shows the interval, the last beacon and the next one due", () => {
    const text = box().text();
    expect(text).toContain("every 30 min");
    expect(text).toContain("2 min ago");
    expect(text).toContain("in 29 min");
  });

  it("says off and a dash for the last and the next beacon when the beacon is off and nothing was sent", () => {
    const text = box({ beacon_interval_min: 0, beacon_last_sent: null, beacon_next_due: null }).text();
    expect(text).toContain("off");
    expect(text).toMatch(/Last beacon\s*-/);
    expect(text).toMatch(/Next due\s*-/);
  });

  it("shows the status last sent in one line, with the state of the radio when a radio makes it, and only while there is a status", () => {
    const line = (wrapper: ReturnType<typeof box>) => wrapper.findAll("dt").find((t) => t.text() === "Status")?.element.nextElementSibling?.textContent;
    expect(box({}, true, {}).text()).not.toContain("Status");
    expect(line(box())).toBe("-");
    expect(line(box({ station_status: "QRV 14.074 MHz USB" }))).toBe("QRV 14.074 MHz USB");
    expect(line(box({ station_status: "QRV 14.074 MHz USB", rig_state: "on" }))).toBe("QRV 14.074 MHz USB · rigctld on");
    expect(line(box({ station_status: "", rig_state: "off" }))).toBe("- · rigctld off");
  });

  it("shows nothing it does not know before the status has come", () => {
    const wrapper = mount(BeaconBox, { props: { status: null, connected: true, now: NOW } });
    expect(wrapper.text()).toContain("Beacon");
    expect(wrapper.text()).toMatch(/Next due\s*-/);
  });

  it("asks twice before it sends", async () => {
    const wrapper = box();
    const button = wrapper.find("button");
    expect(button.text()).toBe("Beacon now");
    await button.trigger("click");
    expect(wrapper.emitted("send")).toBeUndefined();
    expect(button.text()).toBe("Really send?");
    expect(button.classes()).toContain("danger");
    await button.trigger("click");
    expect(wrapper.emitted("send")).toHaveLength(1);
    expect(button.text()).toBe("Beacon now");
  });

  it("forgets the first click after a few seconds", async () => {
    const wrapper = box();
    const button = wrapper.find("button");
    await button.trigger("click");
    vi.advanceTimersByTime(5001);
    await wrapper.vm.$nextTick();
    expect(button.text()).toBe("Beacon now");
    await button.trigger("click");
    expect(wrapper.emitted("send")).toBeUndefined();
  });

  it("is disabled while the TNC is not connected, and the first click is forgotten when it drops", async () => {
    const wrapper = box();
    await wrapper.find("button").trigger("click");
    await wrapper.setProps({ connected: false });
    const button = wrapper.find("button");
    expect(button.attributes("disabled")).toBeDefined();
    expect(button.text()).toBe("Beacon now");
    await wrapper.setProps({ connected: true });
    await wrapper.find("button").trigger("click");
    expect(wrapper.emitted("send")).toBeUndefined();
    expect(box({}, false).find("button").attributes("disabled")).toBeDefined();
  });

  describe("Send status now", () => {
    const buttons = (wrapper: ReturnType<typeof box>) => wrapper.findAll("button");

    it("is a second primary button of the same kind beside the status, there only while there is a status", () => {
      const [beacon, status] = buttons(box());
      expect([beacon?.text(), status?.text()]).toEqual(["Beacon now", "Send status now"]);
      expect([beacon?.classes(), status?.classes()]).toEqual([expect.arrayContaining(["btn", "primary"]), expect.arrayContaining(["btn", "primary"])]);
      expect(buttons(box({}, true, {}))).toHaveLength(1);
    });

    it("asks twice before it sends", async () => {
      const wrapper = box();
      const status = buttons(wrapper)[1];
      await status?.trigger("click");
      expect(wrapper.emitted("send-status")).toBeUndefined();
      expect(status?.text()).toBe("Really send?");
      expect(status?.classes()).toContain("danger");
      await status?.trigger("click");
      expect(wrapper.emitted("send-status")).toHaveLength(1);
      expect(wrapper.emitted("send")).toBeUndefined();
      expect(status?.text()).toBe("Send status now");
    });

    it("is armed one at a time: arming the other button forgets the first", async () => {
      const wrapper = box();
      await buttons(wrapper)[1]?.trigger("click");
      await buttons(wrapper)[0]?.trigger("click");
      expect(buttons(wrapper)[1]?.text()).toBe("Send status now");
      expect(buttons(wrapper)[0]?.text()).toBe("Really send?");
    });

    it("is off while the TNC is not connected, and so are both while the settings below hold changes that are not saved", () => {
      expect(buttons(box({}, false))[1]?.attributes("disabled")).toBeDefined();
      const wrapper = box({}, true, { statusOn: true, unsaved: true });
      expect(buttons(wrapper).map((b) => [b.attributes("disabled") !== undefined, b.attributes("title")])).toEqual([
        [true, "Save your changes first"],
        [true, "Save your changes first"],
      ]);
    });
  });
});
