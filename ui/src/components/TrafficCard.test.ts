// The card of a ship or an aircraft over the map (components/TrafficCard.vue): its full name, its facts, the line that it was only received, and the cross that closes it.
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import TrafficCard from "@/components/TrafficCard.vue";
import { NOW, aircraftRow, ship } from "@/test/fixtures";

describe("the card of a ship or an aircraft", () => {
  it("shows the ship's name in full, its facts and that it was received over the internet only", async () => {
    const wrapper = mount(TrafficCard, { props: { pick: { kind: "ship", key: "230145760" }, ship: ship({ name: "SUOMENLINNA II" }), now: NOW } });
    expect(wrapper.get(".card-call").text()).toBe("Ship SUOMENLINNA II");
    const terms = wrapper.findAll("dt").map((d) => d.text());
    expect(terms).toContain("Call sign");
    expect(wrapper.text()).toContain("OJSU");
    expect(wrapper.text()).toContain("HARBOUR ASSISTANCE");
    expect(wrapper.text()).toContain("never sent on the air");
    await wrapper.get(".card-close").trigger("click");
    expect(wrapper.emitted("close")).toHaveLength(1);
  });

  it("shows an aircraft's flight, type and altitude", () => {
    const wrapper = mount(TrafficCard, { props: { pick: { kind: "aircraft", key: "461fa7" }, aircraft: aircraftRow(), now: NOW } });
    expect(wrapper.get(".card-call").text()).toBe("Aircraft FIN1336");
    expect(wrapper.text()).toContain("AIRBUS A-321 (A321)");
    expect(wrapper.text()).toContain("3850 ft");
  });
});
