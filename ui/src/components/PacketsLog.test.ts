import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import PacketsLog from "@/components/PacketsLog.vue";
import { packet } from "@/test/fixtures";

const packets = new Map([
  ["1", packet(1, { source: "OH2RDG", summary: "position one" })],
  ["2", packet(2, { source: "OH2PU-9", summary: "status two", kind: "status", tnc2: "OH2PU-9>APOTC1:>on air" })],
  ["3", packet(3, { source: "OH2GBA", direction: "out", summary: "our beacon" })],
]);

describe("PacketsLog", () => {
  it("lists the newest packet first, with the direction, the line and the summary", () => {
    const rows = mount(PacketsLog, { props: { packets } }).findAll("tbody tr");
    expect(rows).toHaveLength(3);
    expect(rows[0]?.text()).toContain("our beacon");
    expect(rows[0]?.text()).toContain("out");
    expect(rows[2]?.text()).toContain("position one");
    expect(rows[2]?.text()).toContain("OH2RDG>APN391");
  });

  it("has a Route column: the route of a packet that was heard, nothing for one we sent, the internet for a third-party packet", () => {
    const wrapper = mount(PacketsLog, {
      props: {
        packets: new Map([
          ["1", packet(1, { route: "via OH2RCH-2" })],
          ["2", packet(2, { route: "via OH7JHF-1 (internet) → OH2RCH-3", via: "OH7JHF-1", source: "OH7JHF-1" })],
          ["3", packet(3, { direction: "out", route: "" })],
        ]),
      },
    });
    expect(wrapper.findAll("thead th").map((th) => th.text())).toEqual(["Time", "Dir", "Packet", "Route", "Summary"]);
    expect(wrapper.findAll("tbody tr").map((tr) => tr.findAll("td")[3]?.text())).toEqual(["", "via OH7JHF-1 (internet) → OH2RCH-3", "via OH2RCH-2"]);
  });

  it("filters by the route too", async () => {
    const wrapper = mount(PacketsLog, {
      props: {
        packets: new Map([
          ["1", packet(1, { route: "direct" })],
          ["2", packet(2, { route: "via OH2RCH-2" })],
        ]),
      },
    });
    await wrapper.find("input").setValue("direct");
    expect(wrapper.findAll("tbody tr")).toHaveLength(1);
  });

  it("filters by the text of the box", async () => {
    const wrapper = mount(PacketsLog, { props: { packets } });
    await wrapper.find("input").setValue("on air");
    expect(wrapper.findAll("tbody tr")).toHaveLength(1);
    expect(wrapper.find(".foot").text()).toBe("1 of 3 packets");
  });

  it("shows what was decoded as JSON on a click, and hides it on the next", async () => {
    const wrapper = mount(PacketsLog, { props: { packets } });
    expect(wrapper.find("pre").exists()).toBe(false);
    await wrapper.findAll("tbody tr")[0]?.trigger("click");
    expect(wrapper.find("pre").text()).toContain('"type": "position"');
    await wrapper.findAll("tbody tr")[0]?.trigger("click");
    expect(wrapper.find("pre").exists()).toBe(false);
  });

  it("says in the detail that a time in the packet is the sender's local time", async () => {
    const base = packet(1);
    const local = { ...base, decoded: { ...base.decoded, timestamp: "2026-10-09T23:45:00.000000Z", timestamp_local: true } } as typeof base;
    const wrapper = mount(PacketsLog, { props: { packets: new Map([["1", local]]) } });
    await wrapper.find("tbody tr").trigger("click");
    expect(wrapper.find(".detail").text()).toContain("Time in the packet: 09 23:45 local");
    const plain = mount(PacketsLog, { props: { packets: new Map([["1", base]]) } });
    await plain.find("tbody tr").trigger("click");
    expect(plain.find(".detail").text()).not.toContain("Time in the packet");
  });

  it("keeps the detail of a packet open while newer ones arrive", async () => {
    const live = new Map(packets);
    const wrapper = mount(PacketsLog, { props: { packets: live } });
    await wrapper.findAll("tbody tr")[1]?.trigger("click"); // packet 2
    await wrapper.setProps({ packets: new Map([...live, ["4", packet(4, { summary: "newer" })]]) });
    expect(wrapper.find("pre").exists()).toBe(true);
    expect(wrapper.findAll("tbody tr")[0]?.text()).toContain("newer");
  });
});
