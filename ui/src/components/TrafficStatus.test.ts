// The status row of the groups Ships (AIS) and Aircraft (ADS-B) of the Settings tab (components/TrafficStatus.vue): there only while the tickbox is ticked and the daemon has told the state.
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import TrafficStatus from "@/components/TrafficStatus.vue";
import { fakeDaemon, withDaemon } from "@/test/context";
import { feedState } from "@/test/fixtures";

const traffic = { ais: feedState({ count: 12 }), adsb: feedState({ state: "waiting" }) };

describe("the status row of a feed", () => {
  it("says how many ships are shown while the tickbox is ticked, and is not there while it is not", () => {
    const daemon = fakeDaemon({ traffic });
    const on = mount(TrafficStatus, { props: { feed: "ais", draft: { "ais/enabled": "true" } }, global: withDaemon(daemon) });
    expect(on.text()).toContain("Digitraffic · 12 ships within 450 km");
    const off = mount(TrafficStatus, { props: { feed: "ais", draft: { "ais/enabled": "false" } }, global: withDaemon(daemon) });
    expect(off.text()).toBe("");
  });

  it("says that the aircraft wait for a position", () => {
    const wrapper = mount(TrafficStatus, { props: { feed: "adsb", draft: { "adsb/enabled": "true" } }, global: withDaemon(fakeDaemon({ traffic })) });
    expect(wrapper.text()).toContain("Waiting for your position");
  });
});
