import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import BeaconStatus from "@/components/BeaconStatus.vue";
import { NOW, ago, gpsOff, gpsState, status } from "@/test/fixtures";

type Props = Partial<InstanceType<typeof BeaconStatus>["$props"]>;
const block = (props: Props = {}) =>
  mount(BeaconStatus, {
    props: { status: status({ beacon_last_sent: ago(240) }), gps: gpsOff(), values: {}, now: NOW, armed: false, disabled: false, ...props },
  });

describe("BeaconStatus", () => {
  it("has the label, the state on a pill, one plain line and the button, as the radio's", () => {
    const wrapper = block();
    expect(
      [...wrapper.find(".beaconhead").element.children].map((c) => (c.classList.contains("statetext") ? "statetext" : (c.className.split(" ")[0] ?? ""))),
    ).toEqual(["beaconlabel", "statetext", "tncstatus", "btn"]);
    expect(wrapper.find(".tncstatus").text()).toBe("Last beacon 4 min ago · no timed beacon");
    expect(wrapper.find(".mobileline").exists()).toBe(false);
    expect(wrapper.find(".problem").exists()).toBe(false);
  });

  it("asks twice in words: the button says Really send? and takes the danger colour while armed, and a press is passed on", async () => {
    const wrapper = block();
    expect(wrapper.find("button").text()).toBe("Beacon now");
    await wrapper.find("button").trigger("click");
    expect(wrapper.emitted("press")).toHaveLength(1);
    await wrapper.setProps({ armed: true });
    expect(wrapper.find("button").text()).toBe("Really send?");
    expect(wrapper.find("button").classes()).toContain("danger");
  });

  it("is off, with the reason on hover, when the tab says so", () => {
    const wrapper = block({ disabled: true, why: "Saving…" });
    expect(wrapper.find("button").attributes("disabled")).toBeDefined();
    expect(wrapper.find("button").attributes("title")).toBe("Saving…");
  });

  it("shows the lines of a moving station under the first, and why there is no fix", () => {
    const wrapper = block({
      gps: gpsState({ state: "no_fix", lat: null, lon: null, fix_at: null, problem: "no satellites" }),
      values: { "gps/source": "gpsd" },
    });
    expect(wrapper.find(".beaconlabel").text()).toBe("GPS");
    expect(wrapper.find(".statetext").classes()).toContain("gps-no_fix");
    expect(wrapper.find(".mobileline").text()).toBe("No beacon: no GPS fix");
    expect(wrapper.find(".problem").text()).toBe("no satellites");
    expect(wrapper.find(".beaconhead + .mobileline + .problem").exists()).toBe(true);
  });

  it("shows the GPS state and the fix line with Beacon off under them while the beacon is Off, and the button off", () => {
    const wrapper = block({ gps: gpsState(), values: { "gps/source": "gpsd", "beacon/interval_min": "0" }, disabled: true, why: "The beacon is off" });
    expect(wrapper.find(".beaconlabel").text()).toBe("GPS");
    expect(wrapper.find(".statetext").text()).toBe("fix");
    expect(wrapper.find(".tncstatus").text()).toContain("Fix: 60.4295 N 24.1452 E");
    expect(wrapper.find(".mobileline").text()).toBe("Beacon off");
    expect(wrapper.find("button").attributes("disabled")).toBeDefined();
  });

  it("follows the clock", async () => {
    const wrapper = block({ gps: gpsState() });
    await wrapper.setProps({ now: NOW + 58_000 });
    expect(wrapper.find(".tncstatus").text()).toContain("1 min ago");
  });
});
