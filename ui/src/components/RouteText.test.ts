import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import RouteText from "@/components/RouteText.vue";

describe("RouteText", () => {
  it("writes the route as it is, with a space between the words", () => {
    expect(mount(RouteText, { props: { text: "via a repeater → OH2RCH-2" } }).text()).toBe("via a repeater → OH2RCH-2");
  });

  it("keeps every word together, so that a line breaks only between words and never inside a callsign", () => {
    const words = mount(RouteText, { props: { text: "via OH2RCH-2" } }).findAll(".nowrap");
    expect(words.map((w) => w.text())).toEqual(["via", "OH2RCH-2"]);
  });

  it("is empty for no route", () => {
    expect(mount(RouteText, { props: { text: "" } }).text()).toBe("");
  });
});
