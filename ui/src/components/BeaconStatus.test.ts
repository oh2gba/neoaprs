import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import BeaconStatus from "@/components/BeaconStatus.vue";
import { NOW, ago, gpsOff, gpsState, status } from "@/test/fixtures";

type Props = Partial<InstanceType<typeof BeaconStatus>["$props"]>;
const block = (props: Props = {}) =>
  mount(BeaconStatus, { props: { status: status({ beacon_last_sent: ago(240) }), gps: gpsOff(), values: {}, now: NOW, ...props } });

describe("BeaconStatus", () => {
  it("is the status row of the radio: the state, one plain line, and no button (Beacon now is a row of its own)", () => {
    const wrapper = block();
    expect(wrapper.find("details.statusfold").exists()).toBe(true);
    expect(wrapper.find("summary .statetext").text()).toBe("off");
    expect(wrapper.find(".tncstatus").text()).toBe("Last beacon 4 min ago · no timed beacon");
    expect(wrapper.find("button").exists()).toBe(false);
    expect(wrapper.find(".problem").exists()).toBe(false);
  });

  it("shows the lines of a moving station behind the arrow, and why there is no fix", () => {
    const wrapper = block({
      gps: gpsState({ state: "no_fix", lat: null, lon: null, fix_at: null, problem: "no satellites" }),
      values: { "gps/source": "gpsd" },
    });
    expect(wrapper.find(".statetext").classes()).toContain("gps-no_fix");
    expect(wrapper.find(".igatefold").text()).toBe("No beacon: no GPS fix");
    expect(wrapper.find(".problem").text()).toBe("no satellites");
  });

  it("shows the GPS state and the fix line with Beacon off behind the arrow while the beacon is Off", () => {
    const wrapper = block({ gps: gpsState(), values: { "gps/source": "gpsd", "beacon/interval_min": "0" } });
    expect(wrapper.find(".statetext").text()).toBe("fix");
    expect(wrapper.find(".tncstatus").text()).toContain("Fix: 60.4295 N 24.1452 E");
    expect(wrapper.find(".igatefold").text()).toBe("No automatic beacon · Beacon now still sends");
  });

  it("says off with a detail that adds to it, never the word again, while the beacon is Off", () => {
    const wrapper = block({ values: { "beacon/interval_min": "0" } });
    expect(wrapper.find(".statetext").text()).toBe("off");
    expect(wrapper.find(".tncstatus").text()).toBe("No automatic beacon · Beacon now still sends");
  });

  it("says off in the warn colour and RX only: nothing is sent, with no timer, in RX only", () => {
    const wrapper = block({ values: { "station/transmit": "false" }, status: status({ beacon_interval_min: 60, beacon_last_sent: ago(240) }) });
    expect(wrapper.find(".statetext").text()).toBe("off");
    expect(wrapper.find(".statetext").classes()).toContain("tnc-waiting");
    expect(wrapper.find(".tncstatus").text()).toBe("RX only: nothing is sent");
  });

  it("shows nothing before the daemon has told", () => {
    expect(block({ status: null }).find(".beaconstatus").exists()).toBe(false);
  });

  it("follows the clock", async () => {
    const wrapper = block({ gps: gpsState() });
    await wrapper.setProps({ now: NOW + 58_000 });
    expect(wrapper.find(".tncstatus").text()).toContain("1 min ago");
  });
});
