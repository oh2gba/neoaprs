import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import GroupCompose from "@/components/GroupCompose.vue";

function group(extra: Record<string, unknown> = {}) {
  return mount(GroupCompose, { props: { calls: ["OH2AAA", "OH2BBB", "OH2CCC"], narrow: false, connected: true, ...extra }, attachTo: document.body });
}

describe("GroupCompose", () => {
  it("has the recipients as chips in the header, and under them the text box with 67 left and Send to 3, and no To and no Stations", () => {
    const wrapper = group();
    expect(wrapper.findAll(".convo-head .recipients .chip").map((c) => c.text())).toEqual(["OH2AAA ×", "OH2BBB ×", "OH2CCC ×"]);
    expect(wrapper.find(".compose-left").text()).toBe("67 left");
    expect(wrapper.find(".compose button[type='submit']").text()).toBe("Send to 3");
    expect(wrapper.find("#msg-to").exists()).toBe(false);
    expect(wrapper.find(".compose").text()).not.toContain("Stations");
    expect(Array.from((wrapper.element as HTMLElement).children).map((c) => c.className.split(" ")[0])).toEqual(["convo-head", "group-room", "composebar"]);
    wrapper.unmount();
  });

  it("puts the cursor in the text box", () => {
    const wrapper = group();
    expect(document.activeElement).toBe(wrapper.find("#msg-text").element);
    wrapper.unmount();
  });

  it("takes a recipient out with a click on its chip, and the count follows", async () => {
    const wrapper = group();
    await wrapper.findAll(".chip")[1]?.trigger("click");
    expect(wrapper.emitted("update")).toEqual([[["OH2AAA", "OH2CCC"]]]);
    await wrapper.setProps({ calls: ["OH2AAA", "OH2CCC"] });
    expect(wrapper.find(".compose button[type='submit']").text()).toBe("Send to 2");
    expect(wrapper.findAll(".chip")[0]?.attributes("aria-label")).toBe("Remove OH2AAA");
    wrapper.unmount();
  });

  it("closes when the last recipient is taken out", async () => {
    const wrapper = group({ calls: ["OH2AAA"] });
    await wrapper.find(".chip").trigger("click");
    expect(wrapper.emitted("close")).toHaveLength(1);
    expect(wrapper.emitted("update")).toBeUndefined();
    wrapper.unmount();
  });

  it("closes with a close button on a wide tab and with a back arrow on a narrow one", async () => {
    const wide = group();
    expect(wide.find(".convo-back").exists()).toBe(false);
    await wide.find(".convo-head .xbtn").trigger("click");
    expect(wide.emitted("close")).toHaveLength(1);
    wide.unmount();
    const narrow = group({ narrow: true });
    expect(narrow.find(".convo-head .xbtn").exists()).toBe(false);
    await narrow.find(".convo-back").trigger("click");
    expect(narrow.emitted("close")).toHaveLength(1);
    narrow.unmount();
  });

  it("sends one text to all the recipients, as sendMany", async () => {
    const wrapper = group();
    await wrapper.find("#msg-text").setValue("Net at 20:00");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("sendMany")).toEqual([[["OH2AAA", "OH2BBB", "OH2CCC"], "Net at 20:00"]]);
    wrapper.unmount();
  });

  it("has Send to 3 off while the TNC is not connected", async () => {
    const wrapper = group({ connected: false });
    await wrapper.find("#msg-text").setValue("Hi");
    expect(wrapper.find(".compose button[type='submit']").attributes("disabled")).toBeDefined();
    expect(wrapper.find(".compose button[type='submit']").attributes("title")).toBe("The TNC is not connected");
    wrapper.unmount();
  });
});
