import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import MessageServices from "@/components/MessageServices.vue";
import MessagesPane from "@/components/MessagesPane.vue";
import { MESSAGES_WIDE } from "@/lib/layout";
import { SERVICES } from "@/lib/services";
import { fakeDaemon, withDaemon } from "@/test/context";
import { stubWidth } from "@/test/width";

let width: ReturnType<typeof stubWidth>;
beforeEach(() => {
  width = stubWidth(MESSAGES_WIDE + 120);
  localStorage.clear();
});
afterEach(() => {
  width.restore();
  document.body.innerHTML = "";
});

describe("MessageServices", () => {
  it("lists the services by name, those of one service in a group of its name", () => {
    const wrapper = mount(MessageServices);
    const loose = wrapper.findAll("select > option").map((o) => o.text());
    expect(loose).toEqual(["APRS Thursday", "ANSRVR"]);
    const ota = wrapper.find("optgroup");
    expect(ota.attributes("label")).toBe("APRS OTA");
    expect(ota.findAll("option").map((o) => o.text())).toEqual(["Who is on the air", "Chase an op", "Host an op"]);
    expect(wrapper.find("label").text()).toBe("Services");
  });

  it("writes the chosen one: its addressee and the start of its text, and the browser remembers the choice", async () => {
    const wrapper = mount(MessageServices);
    await wrapper.find("button").trigger("click");
    await wrapper.find("select").setValue("ota_chase");
    expect(wrapper.find("button").attributes("title")).toBe("To OTA: CHASE");
    await wrapper.find("button").trigger("click");
    expect(wrapper.emitted("write")).toEqual([
      ["ANSRVR", "CQ HOTG "],
      ["OTA", "CHASE "],
    ]);
    expect((mount(MessageServices).find("select").element as HTMLSelectElement).value).toBe("ota_chase");
  });

  it("has one entry for each row of the table, each with an addressee and a text", () => {
    expect(mount(MessageServices).findAll("option")).toHaveLength(SERVICES.length);
    expect(SERVICES.every((s) => /^[A-Z0-9-]{1,9}$/.test(s.to) && s.text.trim() !== "")).toBe(true);
  });
});

describe("Services in the Messages tab", () => {
  it("opens the service's conversation with the start of the text in the box, the cursor after it", async () => {
    const daemon = fakeDaemon({ connected: true });
    const wrapper: VueWrapper = mount(MessagesPane, {
      props: {
        conversations: [],
        selected: null,
        thread: [],
        showOverheard: false,
        onSelect: (call: string | null) => void wrapper.setProps({ selected: call }),
      },
      global: withDaemon(daemon),
      attachTo: document.body,
    });
    await flushPromises();
    await wrapper.find(".convlist-services button").trigger("click");
    await flushPromises();
    expect(wrapper.find(".convo-title").text()).toBe("ANSRVR");
    const box = wrapper.find("#msg-text").element as HTMLInputElement;
    expect(box.value).toBe("CQ HOTG ");
    expect(document.activeElement).toBe(box);
    expect(box.selectionStart).toBe("CQ HOTG ".length);
    expect(daemon.send.mock.calls.filter(([c]) => c.cmd === "send_message")).toEqual([]);
  });
});
