import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import PacketsLog from "@/components/PacketsLog.vue";
import { PACKETS_TABLE } from "@/lib/layout";
import { cssRule } from "@/test/css";
import type { RadioRow } from "@/protocol/protocol";
import { fakeDaemon, withDaemon } from "@/test/context";
import { packet, radioRow, radiosTopic } from "@/test/fixtures";
import { stubWidth } from "@/test/width";

const packets = new Map([
  ["1", packet(1, { source: "OH2RDG" })],
  [
    "2",
    packet(2, {
      source: "OH2PU-9",
      kind: "status",
      tnc2: "OH2PU-9>APOTC1:>on air",
      decoded: { type: "status", text: "status two", timestamp: null, locator: null, frequency: null },
    }),
  ],
  ["3", packet(3, { source: "OH2GBA", direction: "out", tnc2: "OH2GBA>APZNEO:!6007.47N/02429.82E- our beacon" })],
]);

describe("PacketsLog", () => {
  it("has the (i) of the tab at the top, which says what the list is", async () => {
    const wrapper = mount(PacketsLog, { props: { packets } });
    expect(wrapper.find(".tablepane").element.firstElementChild?.className).toBe("tab-help");
    await wrapper.find(".tab-help .info-toggle").trigger("click");
    expect(wrapper.find(".tab-help .info-text").text()).toContain("Every packet heard (in) or sent by you (out), newest first");
  });

  it("has the filter in a group box with the legend Filter, as the Stations tab has its filters", () => {
    const wrapper = mount(PacketsLog, { props: { packets } });
    const box = wrapper.find(".tablepane > fieldset.filters");
    expect(box.find("legend").text()).toBe("Filter");
    expect(box.find("input[type='search']").attributes("placeholder")).toBe("Call, text, kind");
  });

  it("lists the newest packet first, with the direction, the line and the summary", () => {
    const rows = mount(PacketsLog, { props: { packets } }).findAll("tbody tr");
    expect(rows).toHaveLength(3);
    expect(rows[0]?.text()).toContain("our beacon");
    expect(rows[0]?.text()).toContain("out");
    expect(rows[2]?.text(), "the summary in the page's words").toContain("Position report · 60.12000 N 24.49000 E");
    expect(rows[2]?.text()).toContain("OH2RDG>APN391");
  });

  it("has a Route column: the route of a packet that was heard, nothing for one we sent, the internet for a third-party packet", () => {
    const wrapper = mount(PacketsLog, {
      props: {
        packets: new Map([
          ["1", packet(1, { route: "via OH2RCH-2" })],
          ["2", packet(2, { route: "via OH7JHF-1 (internet) → OH2RCH-3", via: "rf-gated", gate: "OH7JHF-1", source: "OH7JHF-1" })],
          ["3", packet(3, { direction: "out", route: "" })],
        ]),
      },
    });
    expect(wrapper.findAll("thead th").map((th) => th.text())).toEqual(["Time", "Dir", "Via", "Packet", "Route", "Summary"]);
    expect(wrapper.findAll("tbody tr").map((tr) => tr.findAll("td")[4]?.text())).toEqual(["", "via OH7JHF-1 (internet) → OH2RCH-3", "via OH2RCH-2"]);
  });

  it("has a Via column with how every packet came: the radio's name for the radio's and for ours (FM, also with one radio on), iGate, Internet; with what it means as the title (ours: sent on it)", () => {
    const wrapper = mount(PacketsLog, {
      global: withDaemon(fakeDaemon()),
      props: {
        packets: new Map([
          ["1", packet(1)],
          ["2", packet(2, { via: "rf-gated", gate: "OH7JHF-1", source: "OH7JHF-1", route: "via OH7JHF-1 (internet) → OH2RCH-3" })],
          ["3", packet(3, { via: "is", route: "", path: ["TCPIP*", "qAC", "T2FINLAND"], source: "OH2ABC", tnc2: "OH2ABC>APRS,TCPIP*,qAC,T2FINLAND:>x" })],
          ["4", packet(4, { direction: "out", route: "" })],
          ["5", packet(5, { via: "dummy", source: "QDUMMY-1" })],
        ]),
      },
    });
    const cells = wrapper.findAll("tbody tr").map((tr) => tr.find("td.via"));
    expect(cells.map((td) => td.text())).toEqual(["Dummy", "FM", "Internet", "iGate", "FM"]);
    expect(cells.map((td) => td.attributes("title"))).toEqual([
      "Made up by the Dummy radio, which is no real radio",
      "Sent on radio FM",
      "Received over the internet (APRS-IS), not on the radio",
      "Heard on the radio from an iGate, which took it from the internet; Heard on radio FM",
      "Heard on radio FM",
    ]);
    expect(cells.map((td) => td.classes().includes("internet"))).toEqual([false, false, true, false, false]);
    expect(cssRule(".grid.packets td.via.internet .tag")).toMatch(/font-style:\s*italic/);
    expect(wrapper.findAll("td.via .tag").map((t) => t.classes()[1])).toEqual(["tag-dummy", "tag-neutral", "tag-info", "tag-neutral", "tag-neutral"]);
  });

  it("marks a packet heard on the Mercury radio with a tag of its own, apart from the FM radio's: FM and Mercury", () => {
    const today = radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury", { enabled: false, state: "stopped" }));
    const wrapper = mount(PacketsLog, {
      global: withDaemon(fakeDaemon({ radios: today })),
      props: {
        packets: new Map([
          ["1", packet(1, { radio_id: 1 })],
          ["2", packet(2, { radio_id: 2 })],
        ]),
      },
    });
    const tags = wrapper.findAll("td.via .tag");
    expect(tags.map((t) => t.text())).toEqual(["Mercury", "FM"]);
    expect(tags.map((t) => t.classes()[1])).toEqual(["tag-hf", "tag-neutral"]);
  });

  it("filters by the channel too: Internet finds the packets of the internet, FM the radio's, RF no longer anything", async () => {
    const wrapper = mount(PacketsLog, {
      global: withDaemon(fakeDaemon()),
      props: {
        packets: new Map([
          ["1", packet(1)],
          ["2", packet(2, { via: "is", route: "" })],
        ]),
      },
    });
    await wrapper.find("input[type='search']").setValue("Internet");
    expect(wrapper.findAll("tbody tr.packet-row")).toHaveLength(1);
    await wrapper.find("input[type='search']").setValue("igate");
    expect(wrapper.findAll("tbody tr.packet-row")).toHaveLength(0);
    await wrapper.find("input[type='search']").setValue("fm");
    expect(wrapper.findAll("td.via").map((cell) => cell.text())).toEqual(["FM"]);
    await wrapper.find("input[type='search']").setValue("rf");
    expect(wrapper.findAll("tbody tr.packet-row")).toHaveLength(0);
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
    await wrapper.setProps({ packets: new Map([...live, ["4", packet(4, { tnc2: "OH2NEW>APRS:!6007.47N/02429.82E- newer" })]]) });
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
    expect(wrapper.findAll("thead th").map((th) => th.text())).toEqual(["Time", "Dir", "Via", "Packet", "Route", "Summary"]);
    const row = wrapper.findAll("tbody tr")[2];
    expect(row?.findAll("td")).toHaveLength(6);
    expect(row?.find("td.line").text()).toContain("OH2RDG>APN391");
    expect(row?.find("td.summary").text()).toBe("Position report · 60.12000 N 24.49000 E");
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
    expect(block).toMatch(/"time dir via"\s+"line line line"\s+"route route route"\s+"summary summary summary"/);
    expect(cssRule(".grid.packets.stacked td.route-cell")).toMatch(/font-size:\s*12px/);
    expect(cssRule(".grid.packets.stacked td.summary")).toMatch(/font-size:\s*12px/);
    const cells = cssRule(".grid.packets.stacked tr.packet-row td");
    expect(cells).toMatch(/overflow-wrap:\s*anywhere/);
    expect(cells).toMatch(/word-break:\s*normal/);
    expect(cssRule(".grid.packets.stacked tr.detail td")).toMatch(/display:\s*block/);
  });
});

describe("PacketsLog with several radios", () => {
  const SIX: RadioRow[] = [
    radioRow(1, "kenwood-tnc2"),
    radioRow(2, "mercury"),
    radioRow(3, "kiss", { name: "Shack", number: 2 }),
    radioRow(4, "dummy-hf", { name: "20 m", number: 2 }),
    radioRow(5, "kantronics", { name: "Portable", number: 3, removed: true, enabled: false, state: "stopped" }),
    radioRow(6, "dummy", { name: "Bench", number: 4 }),
  ];
  const packets = new Map([
    ["1", packet(1, { radio_id: 1 })],
    ["2", packet(2, { radio_id: 2 })],
    ["3", packet(3, { radio_id: 3 })],
    ["4", packet(4, { radio_id: 4, via: "dummy" })],
    ["5", packet(5, { radio_id: 5 })],
    ["6", packet(6, { radio_id: 3, via: "rf-gated", gate: "OH7JHF-1", source: "OH7JHF-1" })],
    ["7", packet(7, { radio_id: null, via: "is", route: "" })],
  ]);
  const log = (rows = SIX) => mount(PacketsLog, { props: { packets }, global: withDaemon(fakeDaemon({ radios: radiosTopic(...rows) })) });

  it("names in Via the radio each packet came on, in the tone of its kind, dimmed for a removed one; the iGate's says in its title which radio heard it", () => {
    const wrapper = log();
    const cells = wrapper.findAll("td.via");
    expect(cells.map((cell) => [cell.text(), cell.find(".tag").classes()[1]])).toEqual([
      ["Internet", "tag-info"],
      ["iGate", "tag-neutral"],
      ["Portable", "tag-removed"],
      ["20 m", "tag-dummy"],
      ["Shack", "tag-neutral"],
      ["Mercury", "tag-hf"],
      ["FM", "tag-neutral"],
    ]);
    expect(cells.map((cell) => cell.attributes("title"))).toEqual([
      "Received over the internet (APRS-IS), not on the radio",
      "Heard on the radio from an iGate, which took it from the internet; Heard on radio Shack",
      "Heard on radio Portable",
      "Heard on radio 20 m",
      "Heard on radio Shack",
      "Heard on radio Mercury",
      "Heard on radio FM",
    ]);
  });

  it("filters by a radio's name", async () => {
    const wrapper = log();
    await wrapper.find("input[type='search']").setValue("shack");
    expect(wrapper.findAll("td.via").map((cell) => cell.text())).toEqual(["Shack"]); // (by the word Via shows: the iGate's packet says the radio in its title only)
  });

  it("says in the detail which radio a packet came by", async () => {
    const wrapper = log();
    await wrapper.findAll("tr.packet-row")[2]?.trigger("click");
    const came = wrapper
      .findAll(".packet-detail dt")
      .find((dt) => dt.text() === "Came by")
      ?.element.nextElementSibling?.textContent?.trim();
    expect(came).toBe("Portable - heard on radio Portable");
  });

  it("names the radio for a station with one radio on too (FM, not RF), the HF radio that is off by its name, and gives no tag to a radio the page does not know", () => {
    const wrapper = log([SIX[0], { ...SIX[1], enabled: false, state: "stopped" }]);
    expect(wrapper.findAll("td.via").map((cell) => cell.text())).toEqual(["Internet", "iGate", "", "Dummy", "", "Mercury", "FM"]); // (radios 3 to 6 are not of this station: no tag but the Dummy's mark)
    expect(wrapper.findAll("td.via")[2]?.find(".tag").exists()).toBe(false);
  });
});

describe("PacketsLog with one radio", () => {
  const packets = new Map([
    ["1", packet(1, { radio_id: 1 })],
    ["2", packet(2, { radio_id: 1, direction: "out", route: "" })],
    ["3", packet(3, { radio_id: 1, via: "rf-gated", gate: "OH7JHF-1", source: "OH7JHF-1" })],
    ["4", packet(4, { radio_id: null, via: "is", route: "" })],
  ]);
  const log = (...rows: RadioRow[]) => mount(PacketsLog, { props: { packets }, global: withDaemon(fakeDaemon({ radios: radiosTopic(...rows) })) });
  const via = (wrapper: ReturnType<typeof log>) =>
    wrapper.findAll("td.via").map((cell) => [cell.text(), cell.find(".tag").classes()[1], cell.attributes("title")]);
  const NET = ["Internet", "tag-info", "Received over the internet (APRS-IS), not on the radio"];
  const gate = (name: string) => ["iGate", "tag-neutral", `Heard on the radio from an iGate, which took it from the internet; Heard on radio ${name}`];

  it("names an FM radio with no name of its own FM, a packet of ours as the one heard (its title: sent on it)", () => {
    expect(via(log(radioRow(1, "kenwood-tnc2")))).toEqual([
      NET,
      gate("FM"),
      ["FM", "tag-neutral", "Sent on radio FM"],
      ["FM", "tag-neutral", "Heard on radio FM"],
    ]);
  });

  it("names a radio by the name the operator gave it", () => {
    expect(via(log(radioRow(1, "kenwood-tnc2", { name: "2 m" })))).toEqual([
      NET,
      gate("2 m"),
      ["2 m", "tag-neutral", "Sent on radio 2 m"],
      ["2 m", "tag-neutral", "Heard on radio 2 m"],
    ]);
  });

  it("names an Mercury radio alone Mercury, in its own tone, and a LoRa radio alone LoRa, in its sage", () => {
    expect(via(log(radioRow(1, "mercury"))).slice(2)).toEqual([
      ["Mercury", "tag-hf", "Sent on radio Mercury"],
      ["Mercury", "tag-hf", "Heard on radio Mercury"],
    ]);
    expect(via(log(radioRow(1, "lora-tcp"))).slice(2)).toEqual([
      ["LoRa", "tag-lora", "Sent on radio LoRa"],
      ["LoRa", "tag-lora", "Heard on radio LoRa"],
    ]);
  });

  it("says in the detail that a packet came on that radio, by its name", async () => {
    const wrapper = log(radioRow(1, "kenwood-tnc2"));
    await wrapper.findAll("tr.packet-row")[3]?.trigger("click");
    const came = wrapper
      .findAll(".packet-detail dt")
      .find((dt) => dt.text() === "Came by")
      ?.element.nextElementSibling?.textContent?.trim();
    expect(came).toBe("FM - heard on radio FM");
  });
});
