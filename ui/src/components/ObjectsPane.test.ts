import { t } from "@/i18n";
import { mount } from "@vue/test-utils";
import { seen, shown } from "@/test/shown";
import { describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";
import ObjectsPane from "@/components/ObjectsPane.vue";
import { useOwnObjects } from "@/composables/useOwnObjects";
import type { Panel } from "@/composables/usePanel";
import type { Command, OwnObjectRow } from "@/protocol/protocol";
import { fakeDaemon, ofRadios, tell, withDaemon, type Given } from "@/test/context";
import { ago, ownObject, radioRow, radiosTopic, status } from "@/test/fixtures";
import { cssRule } from "@/test/css";

function pane(rows: OwnObjectRow[] = []) {
  const table = new Map(rows.map((r) => [r.name, r]));
  const sent: Command[] = [];
  const form = useOwnObjects(table, (command) => (sent.push(command), true), {
    show: vi.fn(),
    tab: ref("objects"),
  } as unknown as Panel);
  const wrapper = mount(ObjectsPane, {
    props: { objects: table, form },
    global: withDaemon(fakeDaemon({ fallbackPath: "WIDE1-1,WIDE2-1" })),
  });
  return { wrapper, form, sent, table };
}

const rows = [
  ownObject("LEADER", { comment: "Rescue 1", created_at: ago(900), sent: 3 }),
  ownObject("AID", {
    kind: "item",
    symbol_table: "\\",
    symbol_code: "+",
    created_at: ago(300),
    sent: 1,
    last_sent_at: ago(10),
  }),
];

describe("ObjectsPane", () => {
  it("has an (i) at the top that says what an object is, with a picture", async () => {
    const { wrapper } = pane();
    const bar = wrapper.find(".tab-help");
    expect((wrapper.element as HTMLElement).firstElementChild).toBe(bar.element);
    await bar.find("button.info-toggle").trigger("click");
    expect(bar.find(".info-text").text()).toContain(
      "An object is a marker you put on the map for something that is not a station",
    );
    expect(bar.find(".info-text").text()).toContain("Everyone near you sees it, as long as you send it.");
    expect(bar.find("svg[data-picture='object']").exists()).toBe(true);
  });

  it("says so when there are none, and has the form for a new object under it, with no New button", () => {
    const { wrapper } = pane();
    expect(wrapper.find(".empty").text()).toBe("No objects.");
    expect(wrapper.find(".toolbar").exists()).toBe(false);
    expect(wrapper.findAll("button").some((b) => b.text() === "New")).toBe(false);
    expect(wrapper.find(".objform").exists()).toBe(true);
    expect(wrapper.find("button[type='submit']").text()).toBe("Add");
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

  it("shows the category of an object in plain words as a tag in a column of its own, with its code in the hover, and says that one that is on request is sent only when asked", () => {
    const { wrapper } = pane([
      ownObject("PUB", {
        qru_group: "FOOD",
        on_request: true,
        sent: 0,
        last_sent_at: null,
        next_at: null,
        created_at: ago(900),
      }),
      ownObject("PUMP", { qru_group: "FUEL", created_at: ago(300) }),
      ownObject("PLAIN", { created_at: ago(100) }),
    ]);
    const items = wrapper.findAll(".ownobject");
    const tags = items.map((i) => i.find(".own-tags .tag"));
    expect(tags.map((tag) => (tag.exists() ? tag.text() : null))).toEqual(["Food", "Fuel station", null]);
    expect(tags[0]?.attributes("title")).toBe("Category: Food (FOOD)");
    expect(tags[0]?.classes()).toContain("tag-neutral");
    expect(items[0]?.find(".bulletin-head").text()).not.toContain("Category");
    expect(cssRule(".own-tags")).toMatch(/padding:/);
    // with one radio the column has one tag, at its own width, from the column's left edge
    expect(items.some((i) => i.find(".own-tags").classes().includes("several"))).toBe(false);
    expect(cssRule(".own-tags")).not.toMatch(/display|justify-content|max-width/);
    expect(items.map((i) => i.find(".bulletin-meta").text())).toEqual([
      "sent only when asked",
      "sent 2 times, next in 3 min",
      "sent 2 times, next in 3 min",
    ]);
  });

  describe("the radios of each object, while several radios are on (plan 6: with several, every object says its radio; none is the unmarked default)", () => {
    const FM = radioRow(1, "kenwood-tnc2");
    const HF = radioRow(2, "mercury");
    const list = [
      ownObject("FAR", { radios: [2], qru_group: "FOOD", created_at: ago(900) }),
      ownObject("WIDE", { radios: [1, 2], created_at: ago(600) }),
      ownObject("NEAR", { created_at: ago(300) }),
    ];
    const tagsOf = (station: Given, rows: OwnObjectRow[] = list, given: Given = {}) => {
      const table = new Map(rows.map((r) => [r.name, r]));
      const form = useOwnObjects(table, () => true, { show: vi.fn(), tab: ref("objects") } as unknown as Panel);
      const wrapper = mount(ObjectsPane, {
        props: { objects: table, form },
        global: withDaemon(fakeDaemon({ ...station, ...given })),
      });
      return wrapper
        .findAll(".ownobject")
        .map((i) =>
          i
            .findAll(".own-tags .tag")
            .map((tag) => [seen(tag), tag.attributes("title"), tag.classes().find((c) => c.startsWith("tag-"))]),
        );
    };

    it("tags every object with the radios it goes out on, beside its category, each by its name in its kind's tone", () => {
      expect(tagsOf(ofRadios(FM, HF))).toEqual([
        [
          ["Food", "Category: Food (FOOD)", "tag-neutral"],
          ["Mercury", "Sent on radio Mercury", "tag-hf"],
        ],
        [
          ["Packet", "Sent on radio Packet", "tag-neutral"],
          ["Mercury", "Sent on radio Mercury", "tag-hf"],
        ],
        [["Packet", "Sent on radio Packet", "tag-neutral"]],
      ]);
    });

    it("tags no object with one radio on, whichever it is, as today", () => {
      expect(tagsOf(ofRadios(FM, { ...HF, enabled: false }))).toEqual([
        [["Food", "Category: Food (FOOD)", "tag-neutral"]],
        [],
        [],
      ]);
      expect(tagsOf(ofRadios({ ...FM, enabled: false }, HF))).toEqual([
        [["Food", "Category: Food (FOOD)", "tag-neutral"]],
        [],
        [],
      ]);
      expect(tagsOf(ofRadios(FM, { ...HF, removed: true, enabled: false }))).toEqual([
        [["Food", "Category: Food (FOOD)", "tag-neutral"]],
        [],
        [],
      ]);
    });

    it("shows what is in force: a radio of its own that is off or removed is not shown, and one with none of its own on has no tag and says it waits", () => {
      const rows = [
        ownObject("A", { radios: [1, 3], created_at: ago(900) }),
        ownObject("B", { radios: [3, 4], created_at: ago(600), next_at: ago(120) }),
      ];
      const radios = ofRadios(
        FM,
        HF,
        radioRow(3, "kiss", { number: 2, enabled: false }),
        radioRow(4, "dummy", { number: 3, removed: true, enabled: false }),
      );
      expect(tagsOf(radios, rows, { status: status({ unheard_radio: 2 }) })).toEqual([
        [["Packet", "Sent on radio Packet", "tag-neutral"]],
        [],
      ]);
      const table = new Map(rows.map((r) => [r.name, r]));
      const form = useOwnObjects(table, () => true, { show: vi.fn(), tab: ref("objects") } as unknown as Panel);
      const wrapper = mount(ObjectsPane, { props: { objects: table, form }, global: withDaemon(fakeDaemon(radios)) });
      expect(wrapper.findAll(".ownobject .bulletin-meta").at(1)?.text()).toBe(
        t("schedule.waiting", { n: rows[1]?.sent ?? 0 }),
      );
    });

    it("names the first two of six by their names, then +n whose hover names the rest, a Dummy radio's dashed", () => {
      const six = ofRadios(
        radioRow(1, "kenwood-tnc2", { name: "Shack" }),
        radioRow(2, "mercury", { name: "20m" }),
        radioRow(3, "dummy-hf", { name: "HFdummy" }),
        radioRow(4, "kiss", { name: "Mobile" }),
        radioRow(5, "kiss-tcp", { name: "Remote12" }),
        radioRow(6, "mercury", { name: "40m", number: 2 }),
      );
      const rows = [
        ownObject("ALL", { radios: [1, 2, 3, 4, 5, 6], created_at: ago(900) }),
        ownObject("TWO", { radios: [3, 5], created_at: ago(600) }),
      ];
      expect(tagsOf(six, rows)).toEqual([
        [
          ["Shack", "Sent on radio Shack", "tag-neutral"],
          ["20m", "Sent on radio 20m", "tag-hf"],
          [
            "+4",
            "Sent on radio HFdummy; Sent on radio Mobile; Sent on radio Remote12; Sent on radio 40m",
            "tag-neutral",
          ],
        ],
        [
          ["HFdummy", "Sent on radio HFdummy", "tag-dummy"],
          ["Remote12", "Sent on radio Remote12", "tag-neutral"],
        ],
      ]);
    });

    it("says the radios of its +n to a keyboard and a screen reader as its hover does, and nothing more for the tags of a name", () => {
      const six = ofRadios(...[1, 2, 3].map((id) => radioRow(id, "kiss", { name: `R${id}`, number: id })));
      const table = new Map([ownObject("ALL", { radios: [1, 2, 3] })].map((r) => [r.name, r]));
      const form = useOwnObjects(table, () => true, { show: vi.fn(), tab: ref("objects") } as unknown as Panel);
      const tags = mount(ObjectsPane, { props: { objects: table, form }, global: withDaemon(fakeDaemon(six)) }).findAll(
        ".own-tags .own-radio",
      );
      expect(
        tags.map((tag) => [seen(tag), tag.find(".sr-only").exists() ? tag.find(".sr-only").text() : null]),
      ).toEqual([
        ["R1", null],
        ["R2", null],
        ["+1", "Sent on radio R3"],
      ]);
    });

    it("wraps the tags of a row under each other from the column's left edge rather than take the width of its words on a phone, the column never narrower than its widest tag", () => {
      const table = new Map(list.map((r) => [r.name, r]));
      const form = useOwnObjects(table, () => true, { show: vi.fn(), tab: ref("objects") } as unknown as Panel);
      const several = mount(ObjectsPane, {
        props: { objects: table, form },
        global: withDaemon(fakeDaemon(ofRadios(FM, HF))),
      });
      expect(several.findAll(".own-tags").every((tags) => tags.classes().includes("several"))).toBe(true);
      expect(cssRule(".own-tags.several")).toMatch(/flex-wrap:\s*wrap/);
      expect(cssRule(".own-tags.several")).not.toMatch(/justify-content|max-width/);
      expect(cssRule(".board.ownobjects")).toMatch(/grid-template-columns:\s*minmax\(0, 1fr\) fit-content\(13em\)/);
    });

    it("follows the radios as they are turned on and off", async () => {
      const table = new Map(list.map((r) => [r.name, r]));
      const form = useOwnObjects(table, () => true, { show: vi.fn(), tab: ref("objects") } as unknown as Panel);
      const daemon = fakeDaemon(ofRadios(FM, { ...HF, enabled: false }));
      const wrapper = mount(ObjectsPane, { props: { objects: table, form }, global: withDaemon(daemon) });
      expect(wrapper.findAll(".own-radio")).toHaveLength(0);
      await tell(daemon, { radios: radiosTopic(FM, HF) });
      expect(wrapper.findAll(".own-radio").map((tag) => tag.text())).toEqual([
        "Mercury",
        "Packet",
        "Mercury",
        "Packet",
      ]);
    });
  });

  it("has a symbol for each, from its table and code", () => {
    const { wrapper } = pane(rows);
    expect(wrapper.findAll(".ownobject .symicon")).toHaveLength(2);
  });

  it("has no Edit: a row is selectable, as a row of the Nearby tab is, and has an x as big as the other buttons that says it kills the object on the air", () => {
    const { wrapper } = pane(rows);
    expect(wrapper.findAll("button").some((b) => b.text() === "Edit")).toBe(false);
    expect(wrapper.find(".object-edit").exists()).toBe(false);
    const row = wrapper.find(".ownobject");
    expect(row.attributes("tabindex")).toBe("0");
    expect(row.classes()).toContain("selectable");
    expect(wrapper.find(".bulletin-delete").attributes("title")).toBe("Delete (kill on the air)");
    expect(wrapper.find(".bulletin-delete").classes()).toContain("xbtn");
  });

  it("selects a row on a click: it is highlighted, the form has the object and says Save, and the map is told with the same select event as the Nearby tab's", async () => {
    const { wrapper, form } = pane(rows);
    await wrapper.findAll(".ownobject")[1]?.trigger("click");
    expect(form.editing).toBe("AID");
    expect(wrapper.emitted("select")).toEqual([["AID", false]]);
    const items = wrapper.findAll(".ownobject");
    expect(items[1]?.classes()).toContain("selected");
    expect(items[1]?.attributes("aria-current")).toBe("true");
    expect(items[0]?.classes()).not.toContain("selected");
    expect(items[0]?.attributes("aria-current")).toBeUndefined();
    expect(wrapper.find<HTMLInputElement>("input[maxlength='9']").element.value).toBe("AID");
    expect(wrapper.find("button[type='submit']").text()).toBe("Save");
    await items[0]?.trigger("click", { ctrlKey: true });
    expect(wrapper.emitted("select")?.[1]).toEqual(["LEADER", true]);
    expect(form.editing).toBe("LEADER");
    expect(wrapper.findAll(".ownobject.selected")).toHaveLength(1);
  });

  it("selects a row with Enter or Space, and not from a key pressed on the x in it", async () => {
    const { wrapper, form } = pane(rows);
    await wrapper.findAll(".ownobject")[0]?.trigger("keydown", { key: "Enter" });
    expect(form.editing).toBe("LEADER");
    await wrapper.findAll(".ownobject")[1]?.trigger("keydown", { key: " " });
    expect(form.editing).toBe("AID");
    await wrapper.findAll(".ownobject")[0]?.find(".bulletin-delete").trigger("keydown", { key: "Enter" });
    expect(form.editing).toBe("AID");
    expect(wrapper.emitted("select")).toHaveLength(2);
  });

  it("keeps Space from scrolling the page only on the row itself: on the trash can it is left to the button", () => {
    const { wrapper } = pane(rows);
    const space = (target: Element | undefined): boolean => {
      const event = new KeyboardEvent("keydown", { key: " ", bubbles: true, cancelable: true });
      target?.dispatchEvent(event);
      return event.defaultPrevented;
    };
    const row = wrapper.findAll(".ownobject")[0];
    expect(space(row?.element)).toBe(true);
    expect(space(row?.find(".bulletin-delete").element)).toBe(false);
  });

  it("does not select a row for a click on its x", async () => {
    const { wrapper, form } = pane(rows);
    await wrapper.findAll(".ownobject")[0]?.find(".bulletin-delete").trigger("click");
    expect(form.editing).toBeNull();
    expect(wrapper.emitted("select")).toBeUndefined();
  });

  it("changes the selected object with Save, which sends the one change, and adds a new one with Add when none is selected", async () => {
    const { wrapper, form, sent } = pane(rows);
    await wrapper.findAll(".ownobject")[0]?.trigger("click");
    await wrapper.find<HTMLInputElement>(".objform input[type='text']:not([maxlength])").setValue("Moved");
    await wrapper.find("form").trigger("submit");
    expect(sent).toMatchObject([{ cmd: "object_set", name: "LEADER", comment: "Moved" }]);
    form.cancel();
    await nextTick();
    expect(wrapper.findAll(".ownobject.selected")).toHaveLength(0);
    form.place(60.17, 24.94);
    await wrapper.find<HTMLInputElement>("input[maxlength='9']").setValue("NEWONE");
    expect(wrapper.find("button[type='submit']").text()).toBe("Add");
    await wrapper.find("form").trigger("submit");
    expect(sent[1]).toMatchObject({ cmd: "object_set", name: "NEWONE", kind: "object" });
  });

  it("leaves the selection and clears the form with the Cancel button, for a screen without Esc", async () => {
    const { wrapper, form } = pane(rows);
    await wrapper.findAll(".ownobject")[0]?.trigger("click");
    await wrapper
      .findAll("button")
      .find((b) => b.text() === "Cancel")
      ?.trigger("click");
    expect(form.editing).toBeNull();
    expect(wrapper.findAll(".ownobject.selected")).toHaveLength(0);
    expect(wrapper.find<HTMLInputElement>("input[maxlength='9']").element.value).toBe("");
  });

  it("is three group boxes in a column that scrolls as a whole: Add an object first, My objects, and Local info last", () => {
    const { wrapper } = pane(rows);
    expect([...wrapper.find(".objectspane").element.children].map((c) => c.className.split(" ")[0])).toEqual([
      "tab-help",
      "objectlist",
    ]);
    const list = wrapper.find(".objectlist");
    expect([...list.element.children].map((c) => c.tagName.toLowerCase())).toEqual(["form", "fieldset", "fieldset"]);
    expect(
      [...list.element.querySelectorAll(":scope > form > fieldset > legend, :scope > fieldset > legend")].map((l) =>
        l.textContent?.replace(/\s+/g, " ").replace(/ ?i$/, "").trim(),
      ),
    ).toEqual(["Add an object", "My objects 2", "Local info"]);
    expect(cssRule(".objectlist")).toMatch(/overflow-y:\s*auto/);
    expect(wrapper.find("form.composebar").classes()).toContain("boxed");
    expect(wrapper.find("form.composebar").classes()).not.toContain("scrolls");
  });

  it("brings the form into view when a row is selected, which is above the list", async () => {
    const { wrapper, form } = pane(rows);
    const into = vi.fn();
    wrapper.find<HTMLElement>("form.composebar").element.scrollIntoView = into;
    form.edit("LEADER");
    await nextTick();
    await nextTick();
    expect(into).toHaveBeenCalled();
    expect(wrapper.find("fieldset.composebox > legend").text()).toBe("Edit LEADER");
  });

  it("has Local info as the last group box, in the tab's scroll", async () => {
    const { wrapper } = pane(rows);
    const list = wrapper.find(".objectlist");
    expect(list.element.lastElementChild).toBe(list.find("fieldset.objects-qru").element);
    expect(list.find("fieldset.objects-qru > legend").text().replace(/ ?i$/, "")).toBe("Local info");
    await list.find("fieldset.objects-qru legend button.info-toggle").trigger("click");
    expect(list.find("fieldset.objects-qru legend .info-text .info-line").text()).toBe(
      "Asks stations near you for their objects (APRS QRU): repeaters, events, places. Sent by radio only.",
    );
    const ask = list.find("fieldset.objects-qru .qru-ask button.btn");
    expect(ask.text()).toBe("Ask");
    expect(ask.classes()).not.toContain("primary"); // (the one main action of the tab is Add)
  });

  it("marks a selectable row as one: a hand, a hover, a highlight and a focus ring", () => {
    expect(cssRule(".ownobject.selectable")).toMatch(/cursor:\s*pointer/);
    expect(cssRule(".ownobject.selectable:hover")).toContain("--row-hover");
    expect(cssRule(".ownobject.selected")).toContain("--row-selected");
    expect(cssRule(".ownobject.selectable:focus-visible")).toMatch(/outline:\s*2px solid var\(--accent\)/);
  });

  it("has an x on each that asks twice and then kills the object", async () => {
    const { wrapper, sent } = pane(rows);
    const x = () => wrapper.findAll(".ownobject")[1]?.find(".bulletin-delete");
    expect(shown(x())).toBe("");
    expect(x()?.attributes("aria-label")).toBe("Delete the item AID");
    await x()?.trigger("click");
    expect(shown(x())).toBe("sure?");
    expect(shown(wrapper.findAll(".bulletin-delete")[0])).toBe("");
    expect(sent).toEqual([]);
    await x()?.trigger("click");
    expect(sent).toEqual([{ cmd: "object_kill", name: "AID" }]);
    expect(shown(x())).toBe("");
  });

  it("shows an object that is being killed as such, not selectable and with no x", async () => {
    const { wrapper, form } = pane([ownObject("GONE", { state: "killing", sent: 1 })]);
    const item = wrapper.find(".ownobject");
    expect(item.classes()).toContain("killing");
    expect(item.classes()).not.toContain("selectable");
    expect(item.attributes("tabindex")).toBeUndefined();
    expect(item.find(".bulletin-meta").text()).toBe("killing, sent once");
    expect(item.find(".bulletin-delete").exists()).toBe(false);
    await item.trigger("click");
    expect(form.editing).toBeNull();
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
