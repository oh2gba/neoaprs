import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import MessageCompose from "@/components/MessageCompose.vue";
import { candidates } from "@/lib/recipients";
import { NOW, station } from "@/test/fixtures";

const heard = candidates(
  new Map([station("OH2RDG", { heard_direct: 2 }), station("OH2PU-9"), station("OH3XYZ")].map((s) => [s.call, s] as const)),
  "OH2GBA",
  NOW,
);

function compose(extra: Record<string, unknown> = {}) {
  const wrapper = mount(MessageCompose, { props: { selected: null, connected: true, candidates: heard, ...extra } });
  const to = wrapper.find<HTMLInputElement>("#msg-to");
  const text = wrapper.find<HTMLInputElement>("#msg-text");
  const send = wrapper.find<HTMLButtonElement>("button[type='submit']");
  const open = () => wrapper.find<HTMLButtonElement>("button[aria-expanded]").trigger("click");
  const boxes = () => wrapper.findAll<HTMLInputElement>(".picker-list input[type='checkbox']");
  const chips = () => wrapper.findAll(".recipients .chip");
  return { wrapper, to, text, send, open, boxes, chips };
}

describe("MessageCompose to one station", () => {
  it("is To, Stations, the bytes left, Send and the text, with no list and no chip until Stations is pressed", () => {
    const { wrapper, to, send } = compose();
    expect(to.attributes("placeholder")).toBe("Call");
    expect(wrapper.findAll("button").map((b) => b.text())).toEqual(["Stations", "Send"]);
    expect(send.text()).toBe("Send");
    expect(wrapper.find(".picker").exists()).toBe(false);
    expect(wrapper.find(".recipients").exists()).toBe(false);
    expect(wrapper.find("p").exists()).toBe(false);
  });

  it("sends the one call that is typed as an ordinary message and keeps it in To", async () => {
    const { wrapper, to, text } = compose();
    await to.setValue(" oh2abc-9 ");
    await text.setValue("Moi Pekka");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toEqual([["OH2ABC-9", "Moi Pekka"]]);
    expect(wrapper.emitted("sendMany")).toBeUndefined();
    expect(to.element.value).toBe("OH2ABC-9");
    expect(text.element.value).toBe("");
  });
});

describe("MessageCompose to several stations", () => {
  it("lists the stations heard, the ones heard direct first, with a filter", async () => {
    const { wrapper, open, boxes } = compose();
    await open();
    expect(wrapper.findAll(".picker-list .mono").map((c) => c.text())).toEqual(["OH2RDG", "OH2PU-9", "OH3XYZ"]);
    expect(wrapper.findAll(".picker-list .muted").map((c) => c.text())).toEqual(["direct"]);
    expect(boxes()).toHaveLength(3);
    await wrapper.find("#msg-filter").setValue("pu");
    expect(wrapper.findAll(".picker-list .mono").map((c) => c.text())).toEqual(["OH2PU-9"]);
  });

  it("shows the ticked stations as chips that a click removes, and sends one message to each", async () => {
    const { wrapper, text, boxes, chips, open } = compose();
    await open();
    await boxes()[0]?.setValue(true);
    await boxes()[2]?.setValue(true);
    expect(chips().map((c) => c.text())).toEqual(["OH2RDG ×", "OH3XYZ ×"]);
    await chips()[1]?.trigger("click");
    expect(chips()).toHaveLength(1);
    expect(boxes().map((b) => b.element.checked)).toEqual([true, false, false]);
    await boxes()[1]?.setValue(true);
    await text.setValue("Net at 20:00");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toBeUndefined();
    expect(wrapper.emitted("sendMany")).toHaveLength(1);
    expect(wrapper.emitted("sendMany")?.[0]?.[0]).toEqual(["OH2RDG", "OH2PU-9"]);
    expect(wrapper.emitted("sendMany")?.[0]?.[1]).toBe("Net at 20:00");
    expect(chips()).toHaveLength(0);
    expect(text.element.value).toBe("");
  });

  it("adds a call typed in To with a space or a comma, and includes the call left in To when sending", async () => {
    const { wrapper, to, text, chips } = compose();
    await to.setValue("oh2aaa");
    await to.trigger("keydown", { key: " " });
    expect(chips().map((c) => c.attributes("aria-label"))).toEqual(["Remove OH2AAA"]);
    expect(to.element.value).toBe("");
    await to.setValue("OH2BBB");
    await to.trigger("keydown", { key: "," });
    await to.setValue("OH2CCC");
    await text.setValue("Hello all");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("sendMany")).toEqual([[["OH2AAA", "OH2BBB", "OH2CCC"], "Hello all"]]);
  });

  it("adds a call that is not in the list from the filter box", async () => {
    const { wrapper, text, chips, open } = compose();
    await open();
    await wrapper.find("#msg-filter").setValue("oh9new");
    const add = wrapper.find(".picker-list .chip");
    expect(add.text()).toBe("Add OH9NEW");
    await add.trigger("click");
    expect(chips().map((c) => c.attributes("aria-label"))).toEqual(["Remove OH9NEW"]);
    expect((wrapper.find("#msg-filter").element as HTMLInputElement).value).toBe("");
    await text.setValue("Hi");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toEqual([["OH9NEW", "Hi"]]);
  });

  it("counts the open conversation's call in To as one of the recipients, ticked in the list", async () => {
    const { wrapper, text, boxes, open } = compose({ selected: "OH2RDG" });
    await open();
    expect(boxes().map((b) => b.element.checked)).toEqual([true, false, false]);
    await boxes()[1]?.setValue(true);
    await text.setValue("Hi both");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("sendMany")).toEqual([[["OH2PU-9", "OH2RDG"], "Hi both"]]);
  });

  it("has Send off for a bad call in To even with stations picked, and when the TNC is not connected", async () => {
    const { wrapper, to, text, send, boxes, open } = compose();
    await open();
    await boxes()[0]?.setValue(true);
    await text.setValue("Hi");
    expect(send.element.disabled).toBe(false);
    await to.setValue("oops!");
    expect(send.element.disabled).toBe(true);
    await to.setValue("");
    await wrapper.setProps({ connected: false });
    expect(send.element.disabled).toBe(true);
    expect(send.attributes("title")).toBe("The TNC is not connected");
  });

  it("drops the picked stations when another conversation is opened", async () => {
    const { wrapper, boxes, chips, open, to } = compose();
    await open();
    await boxes()[0]?.setValue(true);
    expect(chips()).toHaveLength(1);
    await wrapper.setProps({ selected: "OH3XYZ" });
    expect(chips()).toHaveLength(0);
    expect(to.element.value).toBe("OH3XYZ");
  });
});
