// The counting of who looks at the HF radio's scope (composables/useScopeLooks.ts): the rows are asked for while at least one pane looks, the page is in front, the modem has the interface and the socket is open, and not otherwise.
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick, shallowRef } from "vue";
import { useScopeLooks } from "@/composables/useScopeLooks";
import type { Connection } from "@/lib/hub";
import { hfState } from "@/test/fixtures";

function setup(scope = true) {
  const send = vi.fn((_command: unknown) => true);
  const hf = shallowRef(hfState());
  if (hf.value.modem) hf.value = { ...hf.value, modem: { ...hf.value.modem, scope } };
  const connection = shallowRef<Connection>("open");
  const visible = shallowRef(true);
  const looks = useScopeLooks(send, hf, connection, visible);
  /** A pane that looks while `looking` is true. */
  const pane = (looking: { value: boolean }) =>
    mount(
      defineComponent({
        setup() {
          looks.look(() => looking.value);
          return () => h("div");
        },
      }),
    );
  const asked = () => send.mock.calls.map(([c]) => c);
  return { looks, pane, asked, connection, visible };
}

describe("who looks at the scope", () => {
  it("asks for the rows when the first pane looks, once for two, and stops when the last one stops", async () => {
    const { looks, pane, asked } = setup();
    const a = shallowRef(false);
    const b = shallowRef(true);
    pane(a);
    pane(b);
    expect(looks.lookers.value).toBe(1);
    expect(asked()).toEqual([{ cmd: "hf_scope", on: true }]);
    a.value = true;
    await nextTick();
    expect(looks.lookers.value).toBe(2);
    expect(asked()).toHaveLength(1);
    b.value = false;
    await nextTick();
    expect(asked()).toHaveLength(1);
    a.value = false;
    await nextTick();
    expect(looks.lookers.value).toBe(0);
    expect(asked().at(-1)).toEqual({ cmd: "hf_scope", on: false });
  });

  it("takes a pane that goes away out of the count, and asks no more when it was the last", () => {
    const { looks, pane, asked } = setup();
    const wrapper = pane(shallowRef(true));
    expect(looks.wanted.value).toBe(true);
    wrapper.unmount();
    expect(looks.lookers.value).toBe(0);
    expect(asked().at(-1)).toEqual({ cmd: "hf_scope", on: false });
  });

  it("asks for nothing while the page is hidden, and when the modem has no scope", () => {
    const hidden = setup();
    hidden.visible.value = false;
    hidden.pane(shallowRef(true));
    expect(hidden.looks.wanted.value).toBe(false);
    expect(hidden.asked()).toEqual([]);
    hidden.visible.value = true;
    expect(hidden.asked()).toEqual([{ cmd: "hf_scope", on: true }]);
    const none = setup(false);
    none.pane(shallowRef(true));
    expect(none.looks.available.value).toBe(false);
    expect(none.asked()).toEqual([]);
  });

  it("asks again when the socket is open anew, and says nothing to a closed one", async () => {
    const { pane, asked, connection } = setup();
    pane(shallowRef(true));
    connection.value = "closed";
    await nextTick();
    expect(asked()).toHaveLength(1);
    connection.value = "open";
    await nextTick();
    expect(asked()).toEqual([
      { cmd: "hf_scope", on: true },
      { cmd: "hf_scope", on: true },
    ]);
  });
});
