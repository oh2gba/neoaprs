import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import PacketsLog from "@/components/PacketsLog.vue";
import { PACKETS_TABLE } from "@/lib/layout";
import { cssRule } from "@/test/css";
import { packet } from "@/test/fixtures";
import { stubWidth } from "@/test/width";

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

  it("shows a readable summary on a click, the raw JSON only under Raw, and hides both on the next", async () => {
    const wrapper = mount(PacketsLog, { props: { packets } });
    expect(wrapper.find(".packet-detail").exists()).toBe(false);
    await wrapper.findAll("tbody tr")[0]?.trigger("click");
    const facts = Object.fromEntries(wrapper.findAll(".packet-detail dt").map((dt) => [dt.text(), dt.element.nextElementSibling?.textContent?.trim()]));
    expect(facts["From"]).toBe("OH2GBA");
    expect(facts["Kind"]).toBe("Position report");
    expect(facts["Position"]).toBe("60.12000 N 24.49000 E");
    const raw = wrapper.find("details.more");
    expect(raw.find("summary").text()).toBe("Raw");
    expect(raw.attributes("open")).toBeUndefined();
    expect(raw.find("pre").text()).toContain('"type": "position"');
    expect(wrapper.find(".packet-detail").text()).not.toMatch(/^\s*\{/);
    await wrapper.findAll("tbody tr")[0]?.trigger("click");
    expect(wrapper.find(".packet-detail").exists()).toBe(false);
  });

  it("never breaks a callsign in a route, in the list or in the detail: the line breaks between the words only", async () => {
    const wrapper = mount(PacketsLog, { props: { packets: new Map([["1", packet(1, { route: "via OH2RCH-2" })]]) } });
    expect(
      wrapper
        .find("td.route-cell")
        .findAll(".nowrap")
        .map((w) => w.text()),
    ).toEqual(["via", "OH2RCH-2"]);
    expect(cssRule(".grid .route-cell")).not.toMatch(/break-all|anywhere/);
    await wrapper.find("tbody tr").trigger("click");
    expect(
      wrapper
        .find(".packet-detail .route")
        .findAll(".nowrap")
        .map((w) => w.text()),
    ).toEqual(["via", "OH2RCH-2"]);
  });
  it("says in the detail that a time in the packet is the sender's local time", async () => {
    const base = packet(1);
    const local = { ...base, decoded: { ...base.decoded, timestamp: "2026-10-09T23:45:00.000000Z", timestamp_local: true } } as typeof base;
    const wrapper = mount(PacketsLog, { props: { packets: new Map([["1", local]]) } });
    await wrapper.find("tbody tr").trigger("click");
    const labels = (w: ReturnType<typeof mount>) => w.findAll(".packet-detail dt").map((dt) => dt.text());
    const sent = wrapper.findAll(".packet-detail dt").find((dt) => dt.text() === "Time in the packet");
    expect(sent?.element.nextElementSibling?.textContent?.trim()).toBe("09 23:45 local");
    const plain = mount(PacketsLog, { props: { packets: new Map([["1", base]]) } });
    await plain.find("tbody tr").trigger("click");
    expect(labels(plain)).not.toContain("Time in the packet");
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

describe("PacketsLog on a narrow tab", () => {
  let width: ReturnType<typeof stubWidth> | undefined;
  afterEach(() => width?.restore());
  /** The page with a tab `size` px wide, once it is measured (the width is taken when the tab is mounted). */
  const narrow = async (size = 380, map = packets) => {
    width = stubWidth(size);
    const wrapper = mount(PacketsLog, { props: { packets: map }, attachTo: document.body });
    await wrapper.vm.$nextTick();
    return wrapper;
  };

  it("is the table of columns while the tab is wide enough, and when its width is not known", async () => {
    const wide = await narrow(PACKETS_TABLE);
    expect(wide.find("table").classes()).not.toContain("stacked");
    expect(wide.find("thead").classes()).not.toContain("sr-only");
    wide.unmount();
    width?.restore();
    expect(mount(PacketsLog, { props: { packets } }).find("table").classes()).not.toContain("stacked");
  });

  it("stacks each packet as one block below that width: the header row for a screen reader only, every cell still there", async () => {
    const wrapper = await narrow(PACKETS_TABLE - 1);
    expect(wrapper.find("table").classes()).toContain("stacked");
    expect(wrapper.find("thead").classes()).toContain("sr-only");
    expect(wrapper.findAll("thead th").map((th) => th.text())).toEqual(["Time", "Dir", "Packet", "Route", "Summary"]);
    const row = wrapper.findAll("tbody tr")[2];
    expect(row?.findAll("td")).toHaveLength(5);
    expect(row?.find("td.line").text()).toContain("OH2RDG>APN391");
    expect(row?.find("td.summary").text()).toBe("position one");
    wrapper.unmount();
  });

  it("follows the width of the tab when it is dragged", async () => {
    const wrapper = await narrow(800);
    expect(wrapper.find("table").classes()).not.toContain("stacked");
    width?.set(380);
    await wrapper.vm.$nextTick();
    expect(wrapper.find("table").classes()).toContain("stacked");
    width?.set(700);
    await wrapper.vm.$nextTick();
    expect(wrapper.find("table").classes()).not.toContain("stacked");
    wrapper.unmount();
  });

  it("keeps the selection, the detail row and the filter working", async () => {
    const wrapper = await narrow();
    await wrapper.find("input").setValue("on air");
    expect(wrapper.findAll("tr.packet-row")).toHaveLength(1);
    expect(wrapper.find(".foot").text()).toBe("1 of 3 packets");
    await wrapper.find("tr.packet-row").trigger("click");
    expect(wrapper.find("tr.packet-row").classes()).toContain("selected");
    expect(wrapper.find("tr.detail .packet-detail").exists()).toBe(true);
    await wrapper.find("tr.packet-row").trigger("keydown", { key: "Enter" });
    expect(wrapper.find("tr.detail").exists()).toBe(false);
    wrapper.unmount();
  });

  it("is drawn as a block with the packet line first, then the route and the summary small, and the packet line is not broken letter by letter", () => {
    const block = cssRule(".grid.packets.stacked tr.packet-row");
    expect(block).toMatch(/display:\s*grid/);
    expect(block).toMatch(/"time dir"\s+"line line"\s+"route route"\s+"summary summary"/);
    expect(cssRule(".grid.packets.stacked td.route-cell")).toMatch(/font-size:\s*12px/);
    expect(cssRule(".grid.packets.stacked td.summary")).toMatch(/font-size:\s*12px/);
    const cells = cssRule(".grid.packets.stacked tr.packet-row td");
    expect(cells).toMatch(/overflow-wrap:\s*anywhere/);
    expect(cells).toMatch(/word-break:\s*normal/);
    expect(cssRule(".grid.packets.stacked tr.detail td")).toMatch(/display:\s*block/);
  });
});
