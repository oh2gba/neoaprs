import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SettingsField from "@/components/SettingsField.vue";
import { bytes, characters, type TextLimit } from "@/lib/textlimit";

const COMMENT: TextLimit = { max: 43, measure: characters, kind: "characters" };

/**
 * A typed setting with a limit, whose value follows what it says (as the settings form's draft
 * does).
 */
function field(value = "", count: TextLimit | null = COMMENT) {
  const wrapper = mount(SettingsField, {
    props: {
      id: "set-station-comment",
      info: { label: "Comment", tip: ["What the beacon says after the position."] },
      modelValue: value,
      fallback: "",
      error: "",
      changed: false,
      apply: true,
      count: count ?? undefined,
      "onUpdate:modelValue": (text: string) => wrapper.setProps({ modelValue: text }),
    },
    attachTo: document.body,
  });
  const input = wrapper.find<HTMLInputElement>("#set-station-comment");
  /** Types (or pastes) so that the field holds `text`, the caret at its end. */
  const type = async (text: string) => {
    input.element.value = text;
    input.element.setSelectionRange(text.length, text.length);
    await input.trigger("input");
  };
  return { wrapper, input, type, counter: () => wrapper.find(".compose-left") };
}

describe("SettingsField with a limit", () => {
  it("has the counter right of the field, before the (i), as the box to write a message in has it", () => {
    const { wrapper, counter } = field("NeoAPRS");
    expect(counter().text()).toBe("36 left");
    expect(counter().attributes("title")).toBe("36 of 43 characters left");
    expect(
      [...wrapper.find(".field-control").element.children].map(
        (c) => c.tagName.toLowerCase() + (c.className ? `.${c.className.split(" ")[0]}` : ""),
      ),
    ).toEqual(["input.input", "span.compose-left", "span.infotip"]);
    wrapper.unmount();
  });

  it("follows the typing", async () => {
    const { wrapper, type, counter } = field();
    expect(counter().text()).toBe("43 left");
    await type("Home");
    expect(counter().text()).toBe("39 left");
    await type("Home QTH");
    expect(counter().text()).toBe("35 left");
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual(["Home QTH"]);
    wrapper.unmount();
  });

  it("takes nothing more at the limit", async () => {
    const { wrapper, input, type, counter } = field("x".repeat(43));
    expect(counter().text()).toBe("0 left");
    await type("x".repeat(43) + "y");
    expect(input.element.value).toBe("x".repeat(43));
    expect(wrapper.props("modelValue")).toBe("x".repeat(43));
    expect(counter().text()).toBe("0 left");
    wrapper.unmount();
  });

  it("cuts a paste longer than the room at the limit, never refuses it whole, the caret at the end of what was kept", async () => {
    const { wrapper, input, type, counter } = field("QTH ");
    await type("QTH " + "a".repeat(60));
    expect(input.element.value).toBe("QTH " + "a".repeat(39));
    expect(input.element.selectionStart).toBe(43);
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual(["QTH " + "a".repeat(39)]);
    expect(counter().text()).toBe("0 left");
    wrapper.unmount();
  });

  it("counts by the bytes where the limit is in bytes: a letter that does not fit whole is not taken", async () => {
    const { wrapper, input, type, counter } = field("abcd", { max: 5, measure: bytes, kind: "bytes" });
    expect(counter().text()).toBe("1 left");
    await type("abcdä");
    expect(input.element.value).toBe("abcd");
    await type("abcde");
    expect(input.element.value).toBe("abcde");
    expect(counter().text()).toBe("0 left");
    wrapper.unmount();
  });

  it("counts an ä as the one character the daemon counts in a comment", async () => {
    const { wrapper, type, counter } = field();
    await type("Mökki");
    expect(counter().text()).toBe("38 left");
    wrapper.unmount();
  });

  it("shows a value stored longer than the limit as it is, says how many are over as a message box does, and lets it only be made shorter", async () => {
    const long = "y".repeat(50);
    const { wrapper, input, type, counter } = field(long);
    expect(input.element.value).toBe(long);
    expect(counter().text()).toBe("7 over");
    expect(counter().classes()).toContain("over");
    await type(long + "z");
    expect(input.element.value).toBe(long);
    await type(long.slice(0, 49));
    expect(input.element.value).toBe(long.slice(0, 49));
    expect(counter().text()).toBe("6 over");
    await type(long.slice(0, 49) + "z");
    expect(input.element.value).toBe(long.slice(0, 49));
    await type("short");
    expect(counter().text()).toBe("38 left");
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual(["short"]);
    wrapper.unmount();
  });

  it("keeps the counter's room at the full limit, so that the field's width does not change with the number of digits", async () => {
    const { wrapper, type, counter } = field();
    const room = () => [counter().attributes("data-room"), counter().attributes("data-over")];
    expect(room()).toEqual(["43 left", "43 over"]);
    await type("x".repeat(40));
    expect(counter().text()).toBe("3 left");
    expect(room()).toEqual(["43 left", "43 over"]);
    await type("x".repeat(43));
    expect(room()).toEqual(["43 left", "43 over"]);
    wrapper.unmount();
  });

  it("lets a keyboard that composes finish, and then keeps of it what fits", async () => {
    const { wrapper, input, counter } = field("x".repeat(41));
    input.element.value = "x".repeat(41) + "にほ";
    input.element.dispatchEvent(new InputEvent("input", { isComposing: true }));
    await wrapper.vm.$nextTick();
    expect(input.element.value).toBe("x".repeat(41) + "にほ");
    input.element.value = "x".repeat(41) + "日本語";
    input.element.dispatchEvent(new InputEvent("input", { isComposing: true }));
    await wrapper.vm.$nextTick();
    expect(input.element.value).toBe("x".repeat(41) + "日本語");
    await input.trigger("compositionend");
    expect(input.element.value).toBe("x".repeat(41) + "日本");
    expect(wrapper.props("modelValue")).toBe("x".repeat(41) + "日本");
    expect(counter().text()).toBe("0 left");
    wrapper.unmount();
  });

  it("has no counter and takes any length without a limit", async () => {
    const { wrapper, input, type } = field("", null);
    expect(wrapper.find(".compose-left").exists()).toBe(false);
    await type("x".repeat(100));
    expect(input.element.value).toBe("x".repeat(100));
    wrapper.unmount();
  });
});
