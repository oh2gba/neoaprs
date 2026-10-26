import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import NearbyQru from "@/components/NearbyQru.vue";
import { fakeDaemon, tell, withDaemon } from "@/test/context";
import { ago, configValues, qruState } from "@/test/fixtures";

function make(given: Parameters<typeof fakeDaemon>[0] = {}) {
  const daemon = fakeDaemon(given);
  const wrapper = mount(NearbyQru, { global: withDaemon(daemon) });
  return { wrapper, daemon };
}
const ask = (wrapper: ReturnType<typeof mount>) => wrapper.find("button.btn");
const pills = (wrapper: ReturnType<typeof mount>) => wrapper.findAll("button.qru-group");
const asked = (text: string) => ({ cmd: "qru_ask", text });

describe("Local info (QRU) in the Nearby tab", () => {
  it("is a section with an (i) that says what it does, with the picture, and says nothing else before something was asked", async () => {
    const { wrapper } = make();
    expect(wrapper.find("h3").text()).toBe("Local info (QRU)");
    await wrapper.find(".nearby-head button.info-toggle").trigger("click");
    expect(wrapper.find(".nearby-head .info-text").text()).toContain("Asks stations near you for local info: repeaters, events, places. Sent by radio only.");
    expect(wrapper.find(".nearby-head svg[data-picture='qru']").exists()).toBe(true);
    expect(ask(wrapper).text()).toBe("Ask");
    expect(wrapper.text()).not.toContain("No answer yet");
    expect(wrapper.find(".qru-servers").exists()).toBe(false);
  });

  it("asks for INFO with the Ask button, and the distance after it when one is typed (km, empty is the servers' own)", async () => {
    const { wrapper, daemon } = make();
    await ask(wrapper).trigger("click");
    await wrapper.find("input.qru-km").setValue("120");
    await ask(wrapper).trigger("click");
    await wrapper.find("input.qru-km").trigger("keydown", { key: "Enter" });
    expect(daemon.send.mock.calls.map(([command]) => command)).toEqual([asked("INFO"), asked("INFO 120"), asked("INFO 120")]);
  });

  it("has an (i) on the distance field, and a wrong distance is red and keeps the button and the tags off", async () => {
    const { wrapper } = make({ qru: qruState() });
    expect(wrapper.find("input.qru-km").attributes("aria-label")).toBe("Distance in km");
    await wrapper.find(".qru-ask button.info-toggle").trigger("click");
    expect(wrapper.find(".qru-ask .info-text").text()).toBe("How far to look. Empty: the servers' own, usually 50 km.");
    for (const wrong of ["0", "20001", "ten", "5 km", "-3"]) {
      await wrapper.find("input.qru-km").setValue(wrong);
      expect(wrapper.find("input.qru-km").classes(), wrong).toContain("invalid");
      expect(ask(wrapper).attributes("disabled"), wrong).toBeDefined();
      expect(pills(wrapper).every((p) => p.attributes("disabled") !== undefined)).toBe(true);
    }
    await wrapper.find("input.qru-km").setValue("20000");
    expect(wrapper.find("input.qru-km").classes()).not.toContain("invalid");
    expect(ask(wrapper).attributes("disabled")).toBeUndefined();
  });

  it("says No answer yet once something was asked and nobody has answered", async () => {
    const { wrapper, daemon } = make();
    await tell(daemon, { qru: qruState({ asked: { text: "INFO", at: ago(5) }, servers: [] }) });
    expect(wrapper.find(".qru-none").text()).toBe("No answer yet");
    await tell(daemon, { qru: qruState() });
    expect(wrapper.find(".qru-none").exists()).toBe(false);
  });

  it("lists each server that answered: its call, its groups as tags with the number of objects, and the line it closed with, quietly", () => {
    const { wrapper } = make({
      qru: qruState({
        servers: [
          ...qruState().servers,
          { call: "W1AW", groups: [{ name: "FOOD", count: 2 }], max_objects: 5, range: 30, unit: "mi", at: ago(5), sent: "", sent_at: null },
        ],
      }),
    });
    expect(wrapper.find("h3").text()).toBe("Local info (QRU) 2");
    const rows = wrapper.findAll("li.qru-server");
    expect(rows.map((r) => r.find(".qru-call").text())).toEqual(["DF8LS-10", "W1AW"]);
    expect(rows[0]?.findAll("button.qru-group").map((b) => b.text())).toEqual(["RP70 10", "RP2M 3"]);
    expect(rows[0]?.findAll("button.tag.tag-accent").length).toBe(2);
    expect(rows[0]?.find(".qru-sent").text()).toBe("Sent 5 RP70 Objects Max 5@50km de DF8LS-10");
    expect(rows[1]?.find(".qru-sent").exists()).toBe(false);
  });

  it("asks for a group when its tag is pressed, with the distance of the field", async () => {
    const { wrapper, daemon } = make({ qru: qruState() });
    await pills(wrapper)[1]?.trigger("click");
    await wrapper.find("input.qru-km").setValue("200");
    await pills(wrapper)[0]?.trigger("click");
    expect(pills(wrapper)[0]?.attributes("title")).toBe("Ask DF8LS-10 for RP70");
    expect(daemon.send.mock.calls.map(([command]) => command)).toEqual([asked("RP2M"), asked("RP70 200")]);
  });

  it("is off in RX only, with the reason on hover, and sends nothing", async () => {
    const { wrapper, daemon } = make({ qru: qruState(), config: configValues({ "station/transmit": "false" }) });
    for (const button of [ask(wrapper), ...pills(wrapper)]) {
      expect(button.attributes("disabled")).toBeDefined();
      expect(button.attributes("title")).toBe("RX only: nothing is sent");
      await button.trigger("click");
    }
    await wrapper.find("input.qru-km").trigger("keydown", { key: "Enter" });
    expect(daemon.send).not.toHaveBeenCalled();
  });
});
