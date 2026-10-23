import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import EmailCommands from "@/components/EmailCommands.vue";

const tools = (wrapper: ReturnType<typeof box>) => wrapper.findAll(".mail-tools > button");
function box(connected = true, to = "", own: [string, number][] = []) {
  return mount(EmailCommands, { props: { connected, to, attempts: { own: new Map(own), defaultCount: 6 } } });
}
const form = (wrapper: ReturnType<typeof box>) => wrapper.find(".mail-shortcut");
const submit = (wrapper: ReturnType<typeof box>) => wrapper.find<HTMLButtonElement>(".mail-shortcut button[type='submit']");

describe("EmailCommands", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("has the three buttons, in order, with their titles", () => {
    const buttons = tools(box());
    expect(buttons.map((b) => b.text())).toEqual(["List shortcuts", "Remove shortcut", "Get held mail"]);
    expect(buttons.map((b) => b.attributes("title"))).toEqual(["emails the list to this shortcut's address", "removes this shortcut", undefined]);
  });

  it("lists the shortcut named in To at once, removes it after a second press, and gets the held mail", async () => {
    const wrapper = box(true, "me");
    await tools(wrapper)[0]?.trigger("click");
    await tools(wrapper)[1]?.trigger("click");
    expect(wrapper.emitted("remove")).toBeUndefined();
    await tools(wrapper)[2]?.trigger("click");
    await tools(wrapper)[1]?.trigger("click");
    expect(form(wrapper).exists()).toBe(false);
    expect(wrapper.emitted("list")).toEqual([["me"]]);
    expect(wrapper.emitted("remove")).toEqual([["me"]]);
    expect(wrapper.emitted("get")).toHaveLength(1);
  });

  it("asks for the name there when To is empty, an address or has a space, and sends it with the list", async () => {
    for (const to of ["", "jane@example.com", "me too"]) {
      const wrapper = box(true, to);
      await tools(wrapper)[0]?.trigger("click");
      expect(wrapper.emitted("list")).toBeUndefined();
      expect(submit(wrapper).text()).toBe("List");
      expect(submit(wrapper).attributes("disabled")).toBeDefined();
      await wrapper.find("#mail-shortcut").setValue("not a name");
      expect(submit(wrapper).attributes("disabled")).toBeDefined();
      await wrapper.find("#mail-shortcut").setValue(" me ");
      expect(submit(wrapper).attributes("disabled")).toBeUndefined();
      await form(wrapper).trigger("submit");
      expect(wrapper.emitted("list")).toEqual([["me"]]);
      expect(form(wrapper).exists()).toBe(false);
    }
  });

  it("asks for the name of the shortcut to remove, there, and sends it", async () => {
    const wrapper = box(true, "jane@example.com");
    expect(form(wrapper).exists()).toBe(false);
    await tools(wrapper)[1]?.trigger("click");
    expect(submit(wrapper).text()).toBe("Remove");
    expect(submit(wrapper).attributes("title")).toBe("removes this shortcut");
    expect(submit(wrapper).attributes("disabled")).toBeDefined();
    await wrapper.find("#mail-shortcut").setValue("jane");
    expect(submit(wrapper).attributes("disabled")).toBeUndefined();
    await form(wrapper).trigger("submit");
    expect(wrapper.emitted("remove")).toBeUndefined();
    expect(submit(wrapper).text()).toBe("sure?");
    await form(wrapper).trigger("submit");
    expect(wrapper.emitted("remove")).toEqual([["jane"]]);
    expect(wrapper.emitted("list")).toBeUndefined();
    expect(form(wrapper).exists()).toBe(false);
  });

  it("gives up with Cancel or the button again, sending nothing", async () => {
    const wrapper = box();
    await tools(wrapper)[1]?.trigger("click");
    await wrapper.find("#mail-shortcut").setValue("jane");
    await wrapper.findAll(".mail-shortcut button")[1]?.trigger("click");
    expect(form(wrapper).exists()).toBe(false);
    await tools(wrapper)[1]?.trigger("click");
    await tools(wrapper)[1]?.trigger("click");
    expect(form(wrapper).exists()).toBe(false);
    expect(wrapper.emitted("remove")).toBeUndefined();
  });

  it("switches the open name field from one command to the other", async () => {
    const wrapper = box();
    await tools(wrapper)[0]?.trigger("click");
    await wrapper.find("#mail-shortcut").setValue("me");
    await tools(wrapper)[1]?.trigger("click");
    expect(submit(wrapper).text()).toBe("Remove");
    await form(wrapper).trigger("submit");
    await form(wrapper).trigger("submit");
    expect(wrapper.emitted("remove")).toEqual([["me"]]);
    expect(wrapper.emitted("list")).toBeUndefined();
  });

  it("asks twice before removing a shortcut: the button says sure?, the first press is forgotten after 5 seconds, and nothing else asks", async () => {
    const wrapper = box(true, "me");
    expect(tools(wrapper)[1]?.text()).toBe("Remove shortcut");
    await tools(wrapper)[1]?.trigger("click");
    expect(tools(wrapper)[1]?.text()).toBe("sure?");
    expect(tools(wrapper)[1]?.classes()).toContain("danger");
    expect([tools(wrapper)[0]?.text(), tools(wrapper)[2]?.text()]).toEqual(["List shortcuts", "Get held mail"]);
    await vi.advanceTimersByTimeAsync(5100);
    expect(tools(wrapper)[1]?.text()).toBe("Remove shortcut");
    await tools(wrapper)[1]?.trigger("click");
    expect(wrapper.emitted("remove")).toBeUndefined();
    await wrapper.setProps({ to: "jane" });
    expect(tools(wrapper)[1]?.text()).toBe("Remove shortcut");
    await tools(wrapper)[1]?.trigger("click");
    expect(wrapper.emitted("remove")).toBeUndefined();
    await tools(wrapper)[1]?.trigger("click");
    expect(wrapper.emitted("remove")).toEqual([["jane"]]);
    expect(tools(wrapper)[1]?.text()).toBe("Remove shortcut");
  });

  it("has the gateway's attempts beside the buttons: the setting as the placeholder, saved when changed, cleared by the x", async () => {
    const wrapper = box();
    expect(wrapper.find(".mail-tools .attempts-input").attributes("placeholder")).toBe("(default: 6)");
    expect(wrapper.find(".mail-tools .use-default").exists()).toBe(false);
    await wrapper.find(".mail-tools .attempts-input").setValue("2");
    expect(wrapper.emitted("setAttempts")).toEqual([["EMAIL-2", 2]]);
    const own = box(true, "", [["EMAIL-2", 2]]);
    expect(own.find<HTMLInputElement>(".attempts-input").element.value).toBe("2");
    await own.find(".attemptsbox .use-default").trigger("click");
    expect(own.emitted("clearAttempts")).toEqual([["EMAIL-2"]]);
  });

  it("is off, with the title, while the TNC is not connected", async () => {
    const wrapper = box(false, "me");
    for (const b of tools(wrapper)) {
      expect(b.attributes("disabled")).toBeDefined();
      expect(b.attributes("title")).toBe("The TNC is not connected");
    }
    await tools(wrapper)[0]?.trigger("click");
    expect(wrapper.emitted("list")).toBeUndefined();
  });
});
