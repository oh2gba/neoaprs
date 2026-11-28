// Who looks at the lines put on APRS-IS (useIgateLook): asked while a pane looks, the page is in front and
// the socket is open; said again when the socket was opened anew; stopped when the pane goes.
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { defineComponent, h, ref } from "vue";
import { useIgateLook } from "@/composables/useIgateLook";
import type { Connection } from "@/lib/hub";

function setup() {
  const send = vi.fn(() => true);
  const connection = ref<Connection>("open");
  const visible = ref(true);
  const looking = ref(false);
  let look = null as ReturnType<typeof useIgateLook> | null;
  const pane = defineComponent({
    setup() {
      look = useIgateLook(send, connection, visible);
      look.look(() => looking.value);
      return () => h("div");
    },
  });
  const wrapper = mount(pane);
  return { send, connection, visible, looking, wrapper, look: () => look as ReturnType<typeof useIgateLook> };
}

const sent = (send: ReturnType<typeof setup>["send"]) => send.mock.calls.map((call) => (call as unknown[])[0]);

describe("useIgateLook", () => {
  it("asks while a pane looks and the page is in front, and stops when either ends", () => {
    const { send, visible, looking } = setup();
    expect(sent(send)).toEqual([]);
    looking.value = true;
    visible.value = false;
    visible.value = true;
    looking.value = false;
    expect(sent(send)).toEqual([
      { cmd: "igate_look", on: true },
      { cmd: "igate_look", on: false },
      { cmd: "igate_look", on: true },
      { cmd: "igate_look", on: false },
    ]);
  });

  it("asks again after the socket was opened anew, and says no to nothing while it is closed", () => {
    const { send, connection, looking } = setup();
    looking.value = true;
    connection.value = "closed";
    connection.value = "open";
    expect(sent(send)).toEqual([
      { cmd: "igate_look", on: true },
      { cmd: "igate_look", on: true },
    ]);
  });

  it("stops when the pane goes", () => {
    const { send, looking, wrapper, look } = setup();
    looking.value = true;
    wrapper.unmount();
    expect(look().asked.value).toBe(false);
    expect(sent(send)).toEqual([
      { cmd: "igate_look", on: true },
      { cmd: "igate_look", on: false },
    ]);
  });
});
