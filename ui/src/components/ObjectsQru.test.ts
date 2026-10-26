import { mount } from "@vue/test-utils";
import { shallowRef } from "vue";
import { describe, expect, it } from "vitest";
import ObjectsQru from "@/components/ObjectsQru.vue";
import { fakeDaemon, tell, withDaemon } from "@/test/context";
import { NOW, ago, configValues, qruState, toastOf } from "@/test/fixtures";

function make(given: Parameters<typeof fakeDaemon>[0] = {}) {
  const daemon = fakeDaemon(given);
  const wrapper = mount(ObjectsQru, { global: withDaemon(daemon) });
  return { wrapper, daemon };
}
const ask = (wrapper: ReturnType<typeof mount>) => wrapper.find("button.btn");
const pills = (wrapper: ReturnType<typeof mount>) => wrapper.findAll("button.qru-group");
const asked = (text: string) => ({ cmd: "qru_ask", text });
const row = (wrapper: ReturnType<typeof mount>) => wrapper.find(".qrustatus");
const line = (wrapper: ReturnType<typeof mount>) => row(wrapper).find(".tncstatus").text();

describe("Local info in the Objects tab", () => {
  it("is a group box with an (i) in its legend that says what it does, with the picture, and has no status row before something was asked", async () => {
    const { wrapper } = make();
    expect(wrapper.find("fieldset > legend").text().replace(/ ?i$/, "")).toBe("Local info");
    await wrapper.find(".qru-head button.info-toggle").trigger("click");
    expect(wrapper.findAll(".qru-head .info-text .info-line").map((l) => l.text())).toEqual([
      "Asks stations near you for their objects (APRS QRU): repeaters, events, places. Sent by radio only.",
    ]);
    expect(wrapper.find(".qru-head svg[data-picture='qru']").exists()).toBe(true);
    expect(ask(wrapper).text()).toBe("Ask");
    expect(row(wrapper).exists()).toBe(false);
    expect(wrapper.find(".qru-servers").exists()).toBe(false);
  });

  it("starts the distance at the map's radius, asks for INFO with it, and keeps what is typed (empty is the servers' own); the radius moves the field only until something is typed", async () => {
    const config = shallowRef(configValues());
    const { wrapper, daemon } = make({ config });
    const field = () => (wrapper.find("input.qru-km").element as HTMLInputElement).value;
    expect(field()).toBe("150");
    await ask(wrapper).trigger("click");
    await tell(daemon, { config: configValues({ "map/radius_km": "200" }) });
    expect(field()).toBe("200");
    await wrapper.find("input.qru-km").setValue("120");
    await tell(daemon, { config: configValues({ "map/radius_km": "300" }) });
    expect(field()).toBe("120");
    await ask(wrapper).trigger("click");
    await wrapper.find("input.qru-km").trigger("keydown", { key: "Enter" });
    await wrapper.find("input.qru-km").setValue("");
    await ask(wrapper).trigger("click");
    expect(daemon.send.mock.calls.map(([command]) => command)).toEqual([asked("INFO 150"), asked("INFO 120"), asked("INFO 120"), asked("INFO")]);
  });

  it("has an (i) on the distance field, and a wrong distance is red and keeps the button and the tags off", async () => {
    const { wrapper } = make({ qru: qruState({ asked: null }) });
    expect(wrapper.find("input.qru-km").attributes("aria-label")).toBe("Distance in km");
    await wrapper.find(".qru-ask button.info-toggle").trigger("click");
    expect(wrapper.find(".qru-ask .info-text").text()).toBe("How far to look; it starts at the map radius. Empty: the servers' own, usually 50 km.");
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

  it("says in the status row of the groups when the request was sent and that it waits for answers, for the minute Ask is held", async () => {
    const { wrapper, daemon } = make({ qru: qruState({ asked: { text: "INFO 150", at: ago(5) }, servers: [] }) });
    expect(row(wrapper).classes()).toContain("statusfold");
    expect(row(wrapper).find(".statetext").text()).toBe("Asked");
    expect(row(wrapper).find(".statetext").classes()).toContain("tnc-waiting");
    expect(line(wrapper)).toMatch(/^\d\d:\d\d · waiting for answers…$/);
    await tell(daemon, { qru: qruState({ asked: { text: "INFO 150", at: ago(30) } }) });
    expect(line(wrapper)).toMatch(/waiting for answers…$/);
    expect(wrapper.text()).not.toContain("No answer yet");
  });

  it("says after the minute how many servers answered the request, or that none did (a server of an earlier request does not count)", async () => {
    const { wrapper, daemon } = make({ qru: qruState({ asked: { text: "INFO", at: ago(90) } }) });
    expect(line(wrapper)).toMatch(/^\d\d:\d\d · 1 server answered$/);
    expect(row(wrapper).find(".statetext").classes()).toContain("tnc-connected");
    const other = { ...qruState().servers[0], call: "W1AW", at: ago(40) };
    await tell(daemon, { qru: qruState({ asked: { text: "INFO", at: ago(90) }, servers: [...qruState().servers, other] }) });
    expect(line(wrapper)).toMatch(/2 servers answered$/);
    await tell(daemon, { qru: qruState({ asked: { text: "INFO", at: ago(30) }, servers: qruState().servers.map((s) => ({ ...s, at: ago(600) })) }) });
    await tell(daemon, { qru: qruState({ asked: { text: "INFO", at: ago(61) }, servers: qruState().servers.map((s) => ({ ...s, at: ago(600) })) }) });
    expect(line(wrapper)).toMatch(/^\d\d:\d\d · no answer$/);
    expect(row(wrapper).find(".statetext").classes()).not.toContain("tnc-connected");
  });

  it("opens the row on the request that was sent, and holds Ask for the minute with the time left in its title (the tags too), and frees it after", async () => {
    const { wrapper, daemon } = make({ qru: qruState({ asked: { text: "RP70 150", at: ago(20) } }) });
    await row(wrapper).find("summary").trigger("click");
    expect(row(wrapper).text()).toContain("Last request: RP70 150");
    expect(ask(wrapper).attributes("disabled")).toBeDefined();
    expect(ask(wrapper).attributes("title")).toBe("Next request in 40 s");
    expect(pills(wrapper).every((p) => p.attributes("disabled") !== undefined && p.attributes("title") === "Next request in 40 s")).toBe(true);
    await ask(wrapper).trigger("click");
    await wrapper.find("input.qru-km").trigger("keydown", { key: "Enter" });
    await pills(wrapper)[0]?.trigger("click");
    expect(daemon.send).not.toHaveBeenCalled();
    await tell(daemon, { now: NOW + 41_000 });
    expect(ask(wrapper).attributes("disabled")).toBeUndefined();
    expect(ask(wrapper).attributes("title")).toBeUndefined();
    expect(pills(wrapper)[0]?.attributes("disabled")).toBeUndefined();
  });

  it("shows the daemon's refusal of a request in the row, in the words of its code, and takes it away when the next request has been sent", async () => {
    const { wrapper, daemon } = make();
    await tell(daemon, { lastError: toastOf("qru_ask: the same request was sent a moment ago: wait 12 s", "qru.too_soon", { seconds: 12 }) });
    expect(row(wrapper).find(".statetext").text()).toBe("Not sent");
    expect(line(wrapper)).toBe("only one request for local info per minute: wait 12 s");
    await tell(daemon, { lastError: toastOf("qru_ask: RX only", "transmit.off") });
    expect(line(wrapper)).toContain("RX only");
    await tell(daemon, { qru: qruState({ asked: { text: "INFO", at: ago(1) } }) });
    expect(row(wrapper).find(".statetext").text()).toBe("Asked");
    await tell(daemon, { lastError: toastOf("send_message: no call", "other") });
    expect(row(wrapper).find(".statetext").text()).toBe("Asked");
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
    expect(wrapper.find("legend").text().replace(/ ?i$/, "")).toBe("Local info 2");
    const rows = wrapper.findAll("li.qru-server");
    expect(rows.map((r) => r.find(".qru-call").text())).toEqual(["DF8LS-10", "W1AW"]);
    expect(rows[0]?.findAll("button.qru-group").map((b) => b.text())).toEqual(["70 cm repeater 10", "2 m repeater 3"]);
    expect(rows[0]?.findAll("button.tag.tag-accent").length).toBe(2);
    expect(rows[0]?.find(".qru-sent").text()).toBe("Sent 5 RP70 Objects Max 5@50km de DF8LS-10");
    expect(rows[1]?.find(".qru-sent").exists()).toBe(false);
  });

  it("asks for a group when its tag is pressed, with the distance of the field", async () => {
    const { wrapper, daemon } = make({ qru: qruState({ asked: { text: "INFO", at: ago(90) } }) });
    await pills(wrapper)[1]?.trigger("click");
    await wrapper.find("input.qru-km").setValue("200");
    await pills(wrapper)[0]?.trigger("click");
    expect(pills(wrapper)[0]?.attributes("title")).toBe("Ask DF8LS-10 for 70 cm repeater (RP70)");
    expect(daemon.send.mock.calls.map(([command]) => command)).toEqual([asked("RP2M 150"), asked("RP70 200")]);
  });

  it("shows a group that has no plain name as its code, and asks for it by it", async () => {
    const { wrapper, daemon } = make({
      qru: qruState({
        asked: { text: "INFO", at: ago(90) },
        servers: [{ call: "W1AW", groups: [{ name: "MYNET", count: 4 }], max_objects: 5, range: 50, unit: "km", at: ago(5), sent: "", sent_at: null }],
      }),
    });
    expect(pills(wrapper).map((b) => b.text())).toEqual(["MYNET 4"]);
    expect(pills(wrapper)[0]?.attributes("title")).toBe("Ask W1AW for MYNET");
    await pills(wrapper)[0]?.trigger("click");
    expect(daemon.send.mock.calls.map(([command]) => command)).toEqual([asked("MYNET 150")]);
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
