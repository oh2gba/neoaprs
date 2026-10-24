import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import AppHeader from "@/components/AppHeader.vue";
import IconButton from "@/components/IconButton.vue";
import MessageGlyph from "@/components/MessageGlyph.vue";
import StationsTable from "@/components/StationsTable.vue";
import { fakeDaemon, withDaemon } from "@/test/context";
import { ago, station, table } from "@/test/fixtures";

beforeEach(() => localStorage.clear());

describe("MessageGlyph", () => {
  it("is a decorative envelope in the colour of the text, 16 px unless a size is given", () => {
    const svg = mount(MessageGlyph).find("svg");
    expect(svg.classes()).toContain("msgglyph");
    expect(svg.attributes("aria-hidden")).toBe("true");
    expect(svg.attributes("stroke")).toBe("currentColor");
    expect(svg.attributes("width")).toBe("16");
    expect(
      mount(MessageGlyph, { props: { size: 14 } })
        .find("svg")
        .attributes("width"),
    ).toBe("14");
  });

  it("is the same picture in every place that says message: the icon button, the header's unread badge, the Stations table's row button and its button under an empty result", () => {
    const own = mount(MessageGlyph).find("path").attributes("d");
    const button = mount(IconButton, { props: { kind: "message", label: "Message OH2XYZ" } });
    expect(button.find(".msgglyph path").attributes("d")).toBe(own);
    expect(button.attributes("title")).toBe("Message OH2XYZ");
    const header = mount(AppHeader, { props: { call: "OH2GBA", unread: 2 } });
    expect(header.find("button.headmail .msgglyph path").attributes("d")).toBe(own);
    const stations = table(station("OH2GBA", { is_me: true }), station("OH2RDG", { last_heard: ago(20) }));
    const wrapper = mount(StationsTable, { props: { selected: null }, global: withDaemon(fakeDaemon({ stations, call: "OH2GBA" })) });
    expect(wrapper.find("tr:not(.stranger) td.actions .msgglyph path").attributes("d")).toBe(own);
    return wrapper
      .find("input[type='search']")
      .setValue("OH9NEW")
      .then(() => {
        expect(wrapper.find("tr.stranger button .msgglyph path").attributes("d")).toBe(own);
      });
  });
});
