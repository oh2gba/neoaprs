import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import GpsStatus from "@/components/GpsStatus.vue";
import { NOW, ago, gpsOff, gpsState } from "@/test/fixtures";

const values = { "gps/host": "127.0.0.1:2947", "gps/device": "/dev/ttyUSB1", "gps/baud": "4800" };
const block = (gps: ReturnType<typeof gpsState> | null) => mount(GpsStatus, { props: { gps, values, now: NOW } });

describe("GpsStatus", () => {
  it("is not there before the daemon has told the state of the GPS", () => {
    expect(block(null).find(".gpsstatus").exists()).toBe(false);
  });

  it("has the label, the state on a pill and one plain line, as the radio's", () => {
    const wrapper = block(gpsState());
    expect(wrapper.find(".gpslabel").text()).toBe("GPS");
    expect(wrapper.find(".statepill").text()).toBe("fix");
    expect(wrapper.find(".statepill").classes()).toContain("gps-fix");
    expect(wrapper.find(".tncstatus").text()).toBe("Fix: 60.4295 N 24.1452 E, 48 km/h, course 215°, 103 m, 9 satellites, 2 s ago");
    expect(wrapper.find(".tncstatus").attributes("role")).toBe("status");
    expect(wrapper.find(".problem").exists()).toBe(false);
  });

  it("says Off when there is no source, with no problem line", () => {
    const wrapper = block(gpsOff());
    expect(wrapper.find(".statepill").text()).toBe("off");
    expect(wrapper.find(".tncstatus").text()).toBe("Off");
    expect(wrapper.find(".problem").exists()).toBe(false);
  });

  it("says what it is connecting to, and why it cannot, as a line of its own", () => {
    const wrapper = block(gpsState({ state: "connecting", lat: null, lon: null, problem: "Connection refused" }));
    expect(wrapper.find(".statepill").classes()).toContain("gps-connecting");
    expect(wrapper.find(".tncstatus").text()).toBe("Connecting to gpsd at 127.0.0.1:2947");
    expect(wrapper.find(".problem").text()).toBe("Connection refused");
  });

  it("says there is no fix yet, and what the receiver says of it", () => {
    const wrapper = block(gpsState({ state: "no_fix", lat: null, lon: null, fix_at: null, problem: "the receiver has no position fix yet" }));
    expect(wrapper.find(".statepill").text()).toBe("no fix");
    expect(wrapper.find(".tncstatus").text()).toBe("No fix yet");
    expect(wrapper.find(".problem").text()).toBe("the receiver has no position fix yet");
  });

  it("says a fix that is old was lost, once", () => {
    const wrapper = block(gpsState({ state: "stale", fix_at: ago(180), problem: "the latest fix is 180 s old" }));
    expect(wrapper.find(".statepill").classes()).toContain("gps-stale");
    expect(wrapper.find(".tncstatus").text()).toBe("Fix lost 3 min ago (stale)");
    expect(wrapper.find(".problem").exists()).toBe(false);
  });

  it("follows the clock", async () => {
    const wrapper = block(gpsState());
    await wrapper.setProps({ now: NOW + 58_000 });
    expect(wrapper.find(".tncstatus").text()).toContain("1 min ago");
  });
});
