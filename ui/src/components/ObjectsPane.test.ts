import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import ObjectsPane from "@/components/ObjectsPane.vue";
import { useOwnObjects } from "@/composables/useOwnObjects";
import type { Panel } from "@/composables/usePanel";
import type { Command, OwnObjectRow } from "@/protocol/protocol";
import { NOW, ago, ownObject } from "@/test/fixtures";

function pane(rows: OwnObjectRow[] = []) {
  const table = new Map(rows.map((r) => [r.name, r]));
  const sent: Command[] = [];
  const form = useOwnObjects(table, ref({ lat: 60.17, lon: 24.94 }), (command) => (sent.push(command), true), { show: vi.fn() } as unknown as Panel);
  const wrapper = mount(ObjectsPane, { props: { objects: table, form, fallbackPath: "WIDE1-1,WIDE2-1", now: NOW } });
  return { wrapper, form, sent, table };
}

const rows = [
  ownObject("LEADER", { comment: "Rescue 1", created_at: ago(900), sent: 3 }),
  ownObject("AID", { kind: "item", symbol_table: "\\", symbol_code: "+", created_at: ago(300), sent: 1, last_sent_at: ago(10) }),
];

describe("ObjectsPane", () => {
  it("says so when there are none, and has New", () => {
    const { wrapper } = pane();
    expect(wrapper.find(".empty").text()).toBe("No objects.");
    expect(wrapper.find(".toolbar .btn").text()).toBe("New");
    expect(wrapper.find(".objform").exists()).toBe(false);
  });

  it("lists the objects oldest first with the name, the kind, the comment and how often each was sent and when it goes out next", () => {
    const { wrapper } = pane([...rows].reverse());
    const items = wrapper.findAll(".ownobject");
    expect(items.map((i) => i.find(".bulletin-head strong").text())).toEqual(["LEADER", "AID"]);
    expect(items[0]?.find(".bulletin-head").text()).toContain("object");
    expect(items[1]?.find(".bulletin-head").text()).toContain("item");
    expect(items[0]?.find(".bulletin-text").text()).toBe("Rescue 1");
    expect(items[1]?.find(".bulletin-text").exists()).toBe(false);
    expect(items[0]?.find(".bulletin-meta").text()).toBe("sent 3 times, next in 3 min");
    expect(items[1]?.find(".bulletin-meta").text()).toBe("sent once, next in 3 min");
    expect(wrapper.find(".empty").exists()).toBe(false);
  });

  it("has a symbol for each, from its table and code", () => {
    const { wrapper } = pane(rows);
    expect(wrapper.findAll(".ownobject .symicon")).toHaveLength(2);
  });

  it("opens the form at the place we are when New is pressed", async () => {
    const { wrapper, form } = pane(rows);
    await wrapper.find(".toolbar .btn").trigger("click");
    expect(form.open).toBe(true);
    expect(wrapper.find(".objform").exists()).toBe(true);
    expect(wrapper.find<HTMLInputElement>("input[maxlength='9']").element.value).toBe("");
  });

  it("opens the form with the object when Edit is pressed", async () => {
    const { wrapper, form } = pane(rows);
    await wrapper.find(".ownobject .object-edit").trigger("click");
    expect(form.editing).toBe("LEADER");
    expect(wrapper.find<HTMLInputElement>("input[maxlength='9']").element.value).toBe("LEADER");
  });

  it("has an x on each that asks twice and then kills the object", async () => {
    const { wrapper, sent } = pane(rows);
    const x = () => wrapper.findAll(".ownobject")[1]?.find(".bulletin-delete");
    expect(x()?.text()).toBe("x");
    expect(x()?.attributes("aria-label")).toBe("Kill the item AID");
    await x()?.trigger("click");
    expect(x()?.text()).toBe("sure?");
    expect(wrapper.findAll(".bulletin-delete")[0]?.text()).toBe("x");
    expect(sent).toEqual([]);
    await x()?.trigger("click");
    expect(sent).toEqual([{ cmd: "object_kill", name: "AID" }]);
    expect(x()?.text()).toBe("x");
  });

  it("shows an object that is being killed as such, with neither Edit nor x", () => {
    const { wrapper } = pane([ownObject("GONE", { state: "killing", sent: 1 })]);
    const item = wrapper.find(".ownobject");
    expect(item.classes()).toContain("killing");
    expect(item.find(".bulletin-meta").text()).toBe("killing, sent once");
    expect(item.find(".object-edit").exists()).toBe(false);
    expect(item.find(".bulletin-delete").exists()).toBe(false);
  });

  it("says waiting for an object whose time has passed", () => {
    const { wrapper } = pane([ownObject("LATE", { sent: 0, last_sent_at: null, next_at: ago(120) })]);
    expect(wrapper.find(".bulletin-meta").text()).toBe("not sent yet, waiting");
  });

  it("writes the name and the comment as text, never as markup", () => {
    const { wrapper } = pane([ownObject("<b>x</b>", { comment: "<i>c</i>" })]);
    expect(wrapper.find(".ownobject strong").text()).toBe("<b>x</b>");
    expect(wrapper.find(".ownobject b").exists()).toBe(false);
    expect(wrapper.find(".bulletin-text").text()).toBe("<i>c</i>");
  });
});
