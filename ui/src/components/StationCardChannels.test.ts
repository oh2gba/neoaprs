import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import StationCard from "@/components/StationCard.vue";
import { NOW, ago, station } from "@/test/fixtures";

const fieldsOf = (wrapper: ReturnType<typeof mount>) =>
  Object.fromEntries(wrapper.findAll("dt").map((dt) => [dt.text(), dt.element.nextElementSibling?.textContent?.trim()]));
const card = (row: ReturnType<typeof station>, stations: ReadonlyMap<string, ReturnType<typeof station>> = new Map()) =>
  mount(StationCard, { props: { row, now: NOW, stations } });

const both = station("OH2BOTH", { heard_rf: 3, heard_is: 2, last_rf_at: ago(180), last_is_at: ago(40), last_heard: ago(40), position_via: "is" });
const net = station("OH2NET", {
  heard_rf: 0,
  heard_is: 5,
  last_rf_at: null,
  last_is_at: ago(40),
  last_heard: ago(40),
  position_via: "is",
  last_route: "",
  last_path: [],
  heard_direct: 0,
  heard_via: [],
  best_route: "",
  suggested_path: null,
  can_message: false,
});

describe("the card of a station, by channel", () => {
  it("says when it was last heard for each channel it was heard by: RF 3 min ago · Internet 40 s ago", () => {
    const wrapper = card(both);
    const fields = fieldsOf(wrapper);
    expect(fields["Last heard"]).toBe("RF 3 min ago · Internet 40 s ago");
    const heard = wrapper.findAll("dt").find((dt) => dt.text() === "Last heard")?.element.nextElementSibling;
    expect(heard?.getAttribute("title")).toMatch(/^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/);
  });

  it("names the channel even for a station heard on the radio alone, and the iGate's", () => {
    expect(fieldsOf(card(station("OH2RF", { last_heard: ago(60) })))["Last heard"]).toBe("RF 1 min ago");
    const gated = station("OH2GATED", { heard_rf: 0, heard_rf_gated: 2, last_rf_at: null, last_rf_gated_at: ago(300) });
    expect(fieldsOf(card(gated))["Last heard"]).toBe("iGate 5 min ago");
  });

  it("has the plain age for our own station and our objects, which are not heard by any channel", () => {
    const me = station("OH2GBA", { is_me: true, heard_rf: 0, last_rf_at: null, last_heard: ago(120) });
    expect(fieldsOf(card(me))["Last heard"]).toBe("2 min ago");
  });

  it("says in one plain line for each channel how it reached us: the radio's as ever, the internet's by the iGate that heard it", () => {
    const row = { ...both, internet_reach: { kind: "igate" as const, igate: "OH2GW-10", hops: ["OH2RCH-2"] } };
    const placed = new Map([["OH2GW-10", station("OH2GW-10", { lat: 60.05, lon: 24.3 })]]);
    const fields = fieldsOf(card(row, placed));
    expect(fields["Reached us"]).toBe("via OH2RCH-2");
    expect(fields["Internet"]).toBe("Heard by iGate OH2GW-10 via OH2RCH-2");
    expect(fieldsOf(card(row))["Internet"]).toBe("Heard by iGate OH2GW-10 via OH2RCH-2 (iGate position unknown)");
  });

  it("says of a station that only an app sent from the internet that it never was on the air, and has no radio line for it", () => {
    const fields = fieldsOf(card({ ...net, internet_reach: { kind: "app", igate: "", hops: [] } }));
    expect(fields["Internet"]).toBe("Sent over the internet, not heard on the air");
    expect(fields).not.toHaveProperty("Reached us");
  });

  it("gives an object that came over the internet its internet line, with the station that reported it when an app sent it, and no radio line", () => {
    const object = station("OH2FTJ", {
      kind: "object",
      reported_by: "OH2HCY",
      heard_rf: 0,
      heard_is: 1,
      last_rf_at: null,
      last_is_at: ago(540),
      last_route: "",
      internet_reach: { kind: "app", igate: "", hops: [] },
    });
    const fields = fieldsOf(card(object));
    expect(fields["Internet"]).toBe("Sent over the internet by OH2HCY, not heard on the air");
    expect(fields).not.toHaveProperty("Reached us");
    const heard = station("WELL", {
      kind: "item",
      reported_by: "OH2HCY",
      heard_rf: 0,
      heard_is: 1,
      last_rf_at: null,
      last_route: "",
      internet_reach: { kind: "igate", igate: "OH2GW-10", hops: [] },
    });
    expect(fieldsOf(card(heard))["Internet"]).toBe("Heard by iGate OH2GW-10 directly (iGate position unknown)");
  });

  it("has no internet line for a station nothing came from the internet of, and none for our own station", () => {
    expect(fieldsOf(card(station("OH2RF")))).not.toHaveProperty("Internet");
    const me = station("OH2GBA", { is_me: true, internet_reach: { kind: "app", igate: "", hops: [] } });
    expect(fieldsOf(card(me))).not.toHaveProperty("Internet");
  });

  it("counts the packets by channel under Details, the ones from the internet apart from those of an iGate", () => {
    const wrapper = card(station("OH2ALL", { heard_direct: 1, heard_via: [["OH2RCH-2", 2]], heard_rf_gated: 3, heard_is: 4 }));
    expect(fieldsOf(wrapper)["Heard"]).toBe("1 direct, 2 via OH2RCH-2, 3 via an iGate, 4 over the internet");
  });

  it("says that a message to a station known from the internet alone is not possible, gives it no Message button and no route", () => {
    const wrapper = card(net);
    const fields = fieldsOf(wrapper);
    expect(fields["Messages"]).toBe("Not possible: heard only over the internet, and messages go out by radio");
    expect(fields["Last heard"]).toBe("Internet 40 s ago");
    expect(fields).not.toHaveProperty("Reached us");
    expect(wrapper.find("button.card-message").exists()).toBe(false);
    expect(wrapper.find("button.card-forget").exists()).toBe(true);
  });

  it("does not say it for a station heard on the radio, which keeps its Message button", () => {
    const wrapper = card(both);
    expect(fieldsOf(wrapper)).not.toHaveProperty("Messages");
    expect(wrapper.find("button.card-message").exists()).toBe(true);
  });
});
