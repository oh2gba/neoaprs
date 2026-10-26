import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { shallowRef } from "vue";
import FindRadioToast from "@/components/FindRadioToast.vue";
import SettingsForm from "@/components/SettingsForm.vue";
import { useFindRadio } from "@/composables/useFindRadio";
import type { PortsMessage, RadioSearchMessage } from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon, type Given } from "@/test/context";
import { configValues, tncState } from "@/test/fixtures";

const ports = (find = true): PortsMessage => ({
  type: "ports",
  search: find,
  find,
  ports: [{ device: "/dev/ttyUSB0", description: "FT232R USB UART", hwid: "n/a", vid: null, pid: null }],
});

function make(more: Given = {}, extra: Record<string, string> = {}) {
  const daemon = fakeDaemon({ config: configValues(extra), tnc: tncState(), ports: ports(), ...more });
  const wrapper = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(daemon) });
  const group = wrapper.findAll("fieldset").find((f) => f.find("legend").text() === "Radio");
  if (!group) throw new Error("no Radio group");
  return { wrapper, group, daemon, send: daemon.send };
}

const fold = (group: ReturnType<typeof make>["group"]) => group.find<HTMLDetailsElement>("details.radiostatus");

describe("the TNC group of the Settings tab", () => {
  it("shows the state, the status line and Reconnect, and keeps the fields and the Terminal behind a fold that is closed while the radio is connected", () => {
    const { group } = make();
    expect(fold(group).element.open).toBe(false);
    const head = fold(group).find("summary.statushead");
    expect(head.find(".statetext").text()).toBe("connected");
    expect(head.find(".tncstatus").text()).toBe("Last packet 30 s ago");
    expect(head.find("button").text()).toBe("Reconnect");
    // everything else of the group is inside the fold
    for (const id of ["#set-tnc-profile", "#set-serial-port", "#set-serial-baud", "#find-radio"]) expect(fold(group).find(id).exists(), id).toBe(true);
    expect(
      group.findAll("select, input, .tnclines").every((e) => fold(group).element.contains(e.element) || e.attributes("id") === "set-station-transmit"),
    ).toBe(true);
    expect(group.find("legend").element.nextElementSibling).toBe(group.find(".field").element); // (the Transmit tickbox is the first row)
    expect(group.find(".field").element.nextElementSibling).toBe(fold(group).element);
  });

  it("is open when the radio is not connected, and opens when it stops being connected", async () => {
    expect(fold(make({ tnc: tncState({ state: "waiting", problem: "no KISS frames", path: "" }) }).group).element.open).toBe(true);
    const { group, daemon } = make();
    expect(fold(group).element.open).toBe(false);
    await tell(daemon, { tnc: tncState({ state: "silent", silent_since: null }) });
    expect(fold(group).element.open).toBe(true);
  });

  it("reconnects from the line without opening the fold", async () => {
    const { group, send } = make();
    await fold(group).find("summary button").trigger("click");
    expect(send).toHaveBeenCalledWith({ cmd: "tnc_reconnect" });
    expect(fold(group).element.open).toBe(false);
  });

  it("has the pattern and skip settings nowhere on the page", () => {
    const { wrapper } = make();
    expect(wrapper.find("#set-serial-pattern").exists()).toBe(false);
    expect(wrapper.find("#set-serial-skip").exists()).toBe(false);
  });
});

describe("Find my radio", () => {
  it("is a button of the fold, as big as the buttons beside it, and asks the daemon", async () => {
    const { group, send } = make();
    const button = group.find<HTMLButtonElement>("#find-radio");
    expect(button.text()).toBe("Find my radio");
    expect(button.classes()).toEqual(["btn"]);
    expect(fold(group).element.contains(button.element)).toBe(true);
    await button.trigger("click");
    expect(send).toHaveBeenCalledWith({ cmd: "find_radio" });
    expect(button.element.disabled).toBe(true);
  });

  it("writes nothing beside the button or under the fields", () => {
    const { group } = make();
    const row = group.find(".radiofind");
    expect(row.text()).toBe("Find my radio");
    expect(row.findAll("*")).toHaveLength(1);
  });

  it("is not there where the daemon does not look for the radio among the ports", () => {
    expect(
      make({ ports: ports(false) })
        .group.find("#find-radio")
        .exists(),
    ).toBe(false);
  });

  it("is waiting while a search runs", async () => {
    const daemon = fakeDaemon({ config: configValues(), tnc: tncState(), ports: ports() });
    const wrapper = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(daemon) });
    expect(wrapper.find<HTMLButtonElement>("#find-radio").element.disabled).toBe(false);
    daemon.findRadio.start();
    await wrapper.vm.$nextTick();
    expect(wrapper.find<HTMLButtonElement>("#find-radio").element.disabled).toBe(true);
  });
});

describe("the toast of Find my radio", () => {
  function running() {
    const message = shallowRef<RadioSearchMessage | null>(null);
    const send = vi.fn(() => true);
    const find = useFindRadio(
      message,
      shallowRef(null),
      shallowRef("open" as const),
      send,
      { change: vi.fn(), dismissUndo: vi.fn(), expected: () => "" },
      shallowRef(configValues()),
      () => undefined,
    );
    return { find, message, send };
  }

  it("is not there until a search runs, then says the try and has Cancel", async () => {
    const { find, message, send } = running();
    const wrapper = mount(FindRadioToast, { props: { find } });
    expect(wrapper.find(".toast").exists()).toBe(false);
    find.start();
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".toast").text()).toBe("Looking for the radio…Cancel");
    message.value = { type: "radio_search", state: "trying", port: "/dev/ttyUSB0", baud: 9600, profile: "", number: 2, total: 14 };
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".toast span").text()).toBe("Looking for the radio: /dev/ttyUSB0 at 9600 (2 of 14)");
    await wrapper.find("button").trigger("click");
    expect(send).toHaveBeenLastCalledWith({ cmd: "find_radio_cancel" });
  });

  it("goes when the search ends", async () => {
    const { find, message } = running();
    const wrapper = mount(FindRadioToast, { props: { find } });
    find.start();
    message.value = { type: "radio_search", state: "cancelled", port: "", baud: null, profile: "", number: 0, total: 0 };
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".toast").exists()).toBe(false);
  });
});
