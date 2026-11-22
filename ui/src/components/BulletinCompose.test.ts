import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { LIMITS } from "@/protocol/lists";
import type { OwnBulletinRow, RadioRow } from "@/protocol/protocol";
import { fakeDaemon, ofRadios, tell, withDaemon, type Given } from "@/test/context";
import { cssRule } from "@/test/css";
import { ownBulletin, radioRow, radiosTopic, status, toastOf } from "@/test/fixtures";
import { shown } from "@/test/shown";
import BulletinCompose from "@/components/BulletinCompose.vue";

/** How long the daemon repeats a bulletin (hours) and an announcement (days): the numbers the
 * page has from it (neoaprs/decay.py, by scripts/gen-protocol.py). */
const HOURS = LIMITS.bulletin.repeatHours;
const DAYS = LIMITS.bulletin.announcementRepeatDays;
const many = (n: number, one: string) => `${n} ${n === 1 ? one : `${one}s`}`;

/** The daemon has the post: its row is told. */
const answer = (wrapper: { setProps: (props: { ownBulletins: Map<string, OwnBulletinRow> }) => Promise<void> }, slot: string, text: string) =>
  wrapper.setProps({ ownBulletins: new Map([[slot, ownBulletin(slot, { text })]]) });

function compose() {
  const wrapper = mount(BulletinCompose, { props: { ownBulletins: new Map<string, OwnBulletinRow>() } });
  const kind = wrapper.find<HTMLSelectElement>("#post-kind");
  const id = wrapper.find<HTMLSelectElement>("#post-id");
  const text = wrapper.find<HTMLInputElement>("#post-text");
  const group = wrapper.find<HTMLInputElement>("#post-group");
  const post = wrapper.find<HTMLButtonElement>("button[type='submit']");
  return { wrapper, kind, id, group, text, post };
}

/** The rows of the form as they stand: the label of each, the control it is for, and whether it
 * is greyed. */
function rows(wrapper: ReturnType<typeof compose>["wrapper"]) {
  return wrapper.findAll(".composebar-fields > .field").map((row) => ({
    label: row.find("label").text(),
    control: row.find("label").attributes("for"),
    greyed: row.classes().includes("disabled"),
  }));
}

describe("BulletinCompose", () => {
  it("says in each kind's own words what it does: how long it is sent, by the daemon's numbers, and that a group bulletin is to one group", () => {
    const { kind } = compose();
    expect(kind.findAll("option").map((o) => [o.element.value, o.text()])).toEqual([
      ["bulletin", `Bulletin (sent for ${many(HOURS, "hour")})`],
      ["announcement", `Announcement (sent for ${many(DAYS, "day")})`],
      ["group", `Group bulletin (to one group, sent for ${many(HOURS, "hour")})`],
    ]);
    expect([HOURS, DAYS]).toEqual([4, 3]); // a bulletin for 4 hours, an announcement for 72
    expect(kind.element.value).toBe("bulletin");
  });

  it("has a kind, a number, the group, the text and Post, and no line of help under a field: the help is behind each row's (i)", () => {
    const { wrapper, id, group, post } = compose();
    expect(rows(wrapper)).toEqual([
      { label: "Kind", control: "post-kind", greyed: false },
      { label: "Number", control: "post-id", greyed: false },
      { label: "Group", control: "post-group", greyed: true },
      { label: "Text", control: "post-text", greyed: false },
    ]);
    expect(id.findAll("option").map((o) => o.text())).toEqual([..."0123456789"]);
    expect(id.element.value).toBe("1");
    expect(group.element.disabled).toBe(true);
    expect(shown(post)).toBe("Post");
    expect(wrapper.find("p").exists()).toBe(false);
  });

  it("has an (i) at the end of each of the four rows, named after the row, and none on Send on", async () => {
    const { wrapper, kind } = compose();
    const names = () => wrapper.findAll(".composebar-fields > .field").map((row) => row.find(".info-toggle").attributes("aria-label"));
    expect(names()).toEqual(["About Kind", "About Number", "About Group", "About Text"]);
    for (const row of wrapper.findAll(".composebar-fields > .field")) expect(row.find(".field-control .info-toggle").exists()).toBe(true);
    await kind.setValue("announcement");
    expect(names()[1]).toBe("About Letter");
  });

  it("explains each row in at most two lines, with the daemon's numbers, and the kind's and the group's notes have their pictures", async () => {
    const { wrapper } = compose();
    const open = async (label: string) => {
      await wrapper.find(`.info-toggle[aria-label='About ${label}']`).trigger("click");
      const note = wrapper.find(".info-text");
      return {
        lines: note.findAll(".info-line").map((line) => line.text()),
        picture: note.find("svg.hp").exists() ? note.find("svg.hp").attributes("data-picture") : undefined,
      };
    };
    const kind = await open("Kind");
    expect(kind.picture).toBe("bulletin");
    expect(kind.lines).toHaveLength(2);
    expect(kind.lines.join(" ")).toContain(`sent for ${many(HOURS, "hour")}`);
    expect(kind.lines.join(" ")).toContain(`sent for ${many(DAYS, "day")}`);
    const number = await open("Number");
    expect(number.picture).toBeUndefined();
    expect(number.lines.join(" ")).toContain("replaces it");
    const group = await open("Group");
    expect(group.picture).toBe("bulletingroup");
    expect(group.lines).toHaveLength(2);
    expect(group.lines.join(" ")).toContain("part of the address");
    const text = await open("Text");
    expect(text.lines).toHaveLength(2);
    expect(text.lines[0]).toContain(`${LIMITS.message.textMax} characters`);
  });

  it("moves nothing when the kind changes: the same four rows in the same places, the number's row lettered for an announcement, the group's greyed unless it is a group bulletin", async () => {
    const { wrapper, kind, id, group, text } = compose();
    const places = () => wrapper.findAll(".composebar-fields > .field").map((row) => row.element);
    const form = wrapper.element as HTMLElement;
    const controls = () => [kind.element, id.element, group.element, text.element].map((control) => form.contains(control));
    const before = places();
    const seen: Record<string, ReturnType<typeof rows>> = {};
    for (const value of ["announcement", "group", "bulletin"]) {
      await kind.setValue(value);
      expect(
        places().map((row, at) => row === before[at]),
        value,
      ).toEqual([true, true, true, true]); // (the very rows: none added, none taken out, none made again)
      expect(controls(), value).toEqual([true, true, true, true]);
      seen[value] = rows(wrapper);
    }
    expect(seen["announcement"]?.map((r) => [r.label, r.greyed])).toEqual([
      ["Kind", false],
      ["Letter", false],
      ["Group", true],
      ["Text", false],
    ]);
    expect(seen["group"]?.map((r) => [r.label, r.greyed])).toEqual([
      ["Kind", false],
      ["Number", false],
      ["Group", false],
      ["Text", false],
    ]);
    expect(seen["bulletin"]?.map((r) => [r.label, r.greyed])).toEqual([
      ["Kind", false],
      ["Number", false],
      ["Group", true],
      ["Text", false],
    ]);
    expect(group.element.disabled).toBe(true);
    // the choice is as wide as its row, whatever its options say, and a greyed row keeps its
    // height: the label and the control are dimmed, not hidden
    expect(cssRule(".field-control .input")).toMatch(/flex:\s*1/);
    // and no wider than its row on a phone, in the language with the longest words: the choice, its
    // row and the box may all be narrower than the longest option, which the browser then cuts off
    // in the closed choice (the open list has it whole), as it does the long types of radio
    for (const selector of [".input", ".field-control", "fieldset.composebox"]) expect(cssRule(selector), selector).toMatch(/min-width:\s*0/);
    expect(cssRule(".field")).toMatch(/grid-template-columns:\s*minmax\(7em, min\(36%, 15em\)\) 1fr/);
    expect(cssRule(".input:disabled")).toMatch(/opacity/);
    expect(cssRule(".input:disabled")).not.toMatch(/display|visibility|height/);
  });

  it("keeps what was typed for the group while another kind is chosen, greyed and not sent, and has it back for a group bulletin", async () => {
    const { wrapper, kind, group, text } = compose();
    await kind.setValue("group");
    await group.setValue("hams");
    await kind.setValue("bulletin");
    expect(group.element.value).toBe("hams");
    expect(group.element.disabled).toBe(true);
    await text.setValue("Road closed");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")).toEqual([["BLN1", "Road closed"]]);
    await kind.setValue("group");
    expect(group.element.disabled).toBe(false);
    expect(group.element.value).toBe("HAMS"); // (in capitals, as a post writes it)
  });

  it("does not mark the group wrong while it is greyed", async () => {
    const { wrapper, kind, group } = compose();
    await kind.setValue("group");
    await group.setValue("a b");
    expect(group.classes()).toContain("invalid");
    await kind.setValue("announcement");
    expect(group.classes()).not.toContain("invalid");
    expect(wrapper.find(".field.invalid").exists()).toBe(false);
  });

  it("says Replace on the button while the number, letter or group chosen holds a post of ours, both words in one place so that the button keeps its width", async () => {
    const ours = new Map([
      ["BLN1", ownBulletin("BLN1")],
      ["BLNQ", ownBulletin("BLNQ", { kind: "announcement" })],
      ["BLN3HAMS", ownBulletin("BLN3HAMS", { kind: "group", group: "HAMS", next_at: null })],
    ]);
    const { wrapper, kind, id, group, post } = compose();
    const faces = () => post.findAll(".twowords > span").map((face) => [face.text(), face.classes().includes("twowords-off")]);
    expect(faces()).toEqual([
      ["Post", false],
      ["Replace", true],
    ]);
    await wrapper.setProps({ ownBulletins: ours });
    expect(faces()).toEqual([
      ["Post", true],
      ["Replace", false],
    ]);
    expect(shown(post)).toBe("Replace");
    await id.setValue("2");
    expect(shown(post)).toBe("Post");
    await kind.setValue("announcement");
    expect(shown(post)).toBe("Post"); // (the letter A holds nothing)
    await id.setValue("Q");
    expect(shown(post)).toBe("Replace");
    await kind.setValue("group");
    await id.setValue("3");
    expect(shown(post)).toBe("Post"); // (no group yet)
    await group.setValue("hams");
    expect(shown(post)).toBe("Replace"); // (one whose schedule is over is replaced too)
    await group.setValue("wx");
    expect(shown(post)).toBe("Post");
    expect(cssRule(".twowords > .twowords-off")).toMatch(/visibility:\s*hidden/);
  });

  it("says Post, not Replace, for a group bulletin with no group yet whose number holds a bulletin of ours: a group bulletin never replaces a bulletin", async () => {
    const { wrapper, kind, id, group, post } = compose();
    await wrapper.setProps({ ownBulletins: new Map([["BLN3", ownBulletin("BLN3")]]) });
    await id.setValue("3");
    expect(shown(post)).toBe("Replace");
    await kind.setValue("group");
    expect(id.element.value).toBe("3");
    expect(shown(post)).toBe("Post");
    await group.setValue("a b");
    expect(shown(post)).toBe("Post");
    await group.setValue("hams");
    expect(shown(post)).toBe("Post"); // (BLN3HAMS holds nothing)
  });

  it("replaces: the slot and the new text go to the daemon as a post does", async () => {
    const { wrapper, text, post } = compose();
    await wrapper.setProps({ ownBulletins: new Map([["BLN1", ownBulletin("BLN1", { text: "Road closed" })]]) });
    await text.setValue("Road open again");
    expect(shown(post)).toBe("Replace");
    expect(post.element.disabled).toBe(false);
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")).toEqual([["BLN1", "Road open again"]]);
  });

  it("has Post off until there is a text that can be sent, and counts the 67 characters", async () => {
    const { wrapper, text, post } = compose();
    expect(post.element.disabled).toBe(true);
    expect(wrapper.find(".compose-left").text()).toBe("67 left");
    await text.setValue("Road closed");
    expect(post.element.disabled).toBe(false);
    expect(wrapper.find(".compose-left").text()).toBe("56 left");
    await text.setValue("x".repeat(68));
    expect(text.element.value).toBe("x".repeat(67));
    expect(wrapper.find(".compose-left").text()).toBe("0 left");
    expect(post.element.disabled).toBe(false);
    await text.setValue("a|b");
    expect(post.element.disabled).toBe(true);
  });

  it("posts the slot and the text, and keeps both until the daemon has the bulletin, then empties the text and keeps the kind and the identifier", async () => {
    const { wrapper, id, text } = compose();
    await id.setValue("3");
    await text.setValue(" Snow expected ");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")).toEqual([["BLN3", "Snow expected"]]);
    expect(text.element.value).toBe(" Snow expected ");
    await wrapper.setProps({ ownBulletins: new Map([["BLN3", ownBulletin("BLN3", { text: "Snow expected" })]]) });
    expect(text.element.value).toBe("");
    expect(id.element.value).toBe("3");
  });

  it("keeps the text when the daemon refuses, and a bulletin of the slot with another text is not the answer", async () => {
    const daemon = fakeDaemon();
    const wrapper = mount(BulletinCompose, { props: { ownBulletins: new Map<string, OwnBulletinRow>() }, global: withDaemon(daemon) });
    const text = wrapper.find<HTMLInputElement>("#post-text");
    await text.setValue("Road closed");
    await wrapper.find("form").trigger("submit");
    await wrapper.setProps({ ownBulletins: new Map([["BLN1", ownBulletin("BLN1", { text: "an older text" })]]) });
    await tell(daemon, { lastError: toastOf("bulletin_post: no call", "other") });
    expect(text.element.value).toBe("Road closed");
    await text.setValue("Road open");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")).toEqual([
      ["BLN1", "Road closed"],
      ["BLN1", "Road open"],
    ]);
    await wrapper.setProps({ ownBulletins: new Map([["BLN1", ownBulletin("BLN1", { text: "Road open" })]]) });
    expect(text.element.value).toBe("");
  });

  it("takes the same text posted again to a slot that holds it as done when the row is the daemon's new one, and leaves what was typed since", async () => {
    const { wrapper, text } = compose();
    const first = ownBulletin("BLN1", { text: "same" });
    await wrapper.setProps({ ownBulletins: new Map([["BLN1", first]]) });
    await text.setValue("same");
    await wrapper.find("form").trigger("submit");
    expect(text.element.value).toBe("same");
    await text.setValue("typed meanwhile");
    await wrapper.setProps({ ownBulletins: new Map([["BLN1", ownBulletin("BLN1", { text: "same", sent: 0 })]]) });
    expect(text.element.value).toBe("typed meanwhile");
  });

  it("has lettered identifiers for an announcement, and the number it had is replaced by the first letter", async () => {
    const { wrapper, kind, id, text } = compose();
    await id.setValue("7");
    await kind.setValue("announcement");
    expect(id.findAll("option")).toHaveLength(26);
    expect(id.findAll("option").map((o) => o.text())[0]).toBe("A");
    await text.setValue("Club meeting");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")).toEqual([["BLNA", "Club meeting"]]);
    await answer(wrapper, "BLNA", "Club meeting");
    await id.setValue("Q");
    await text.setValue("Another");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")?.[1]).toEqual(["BLNQ", "Another"]);
    await answer(wrapper, "BLNQ", "Another");
    await kind.setValue("bulletin");
    await text.setValue("Back to numbers");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")?.[2]).toEqual(["BLN0", "Back to numbers"]);
  });

  it("asks for the group of a group bulletin, in capitals, one to five characters: the field takes no more and is red while it is none", async () => {
    const { wrapper, kind, group, text, post } = compose();
    await kind.setValue("group");
    expect(group.element.disabled).toBe(false);
    expect(group.attributes("placeholder")).toBe("Name");
    expect(group.attributes("maxlength")).toBe(String(LIMITS.bulletin.groupMax));
    await text.setValue("Net tonight 20:00");
    expect(post.element.disabled).toBe(true);
    await group.setValue("a b");
    expect(group.classes()).toContain("invalid");
    expect(post.element.disabled).toBe(true);
    await group.setValue("hams");
    expect(group.classes()).not.toContain("invalid");
    expect(post.element.disabled).toBe(false);
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")).toEqual([["BLN1HAMS", "Net tonight 20:00"]]);
    expect(group.element.value).toBe("HAMS");
  });

  it("posts nothing when Enter is pressed on a text that cannot be sent", async () => {
    const { wrapper, text } = compose();
    await text.setValue("a~b");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")).toBeUndefined();
  });
});

describe("Post and Send on, the radios a bulletin goes on", () => {
  /** A station of these radios as the daemon tells them: the topic `radios`. */
  function on(given: Given, ...rows: RadioRow[]) {
    const daemon = fakeDaemon({ ...ofRadios(...rows), ...given });
    const wrapper = mount(BulletinCompose, { props: { ownBulletins: new Map<string, OwnBulletinRow>() }, global: withDaemon(daemon) });
    const sendOn = () => wrapper.find(".field.send-on");
    const ticks = () =>
      sendOn()
        .findAll("label.check")
        .map((tick) => {
          const box = tick.find<HTMLInputElement>("input[type='checkbox']").element;
          return [tick.text(), box.checked, box.disabled];
        });
    const tick = (name: string) =>
      sendOn()
        .findAll("label.check")
        .find((one) => one.text() === name)
        ?.find("input")
        .trigger("change");
    return { wrapper, daemon, sendOn, ticks, tick, post: () => wrapper.find<HTMLButtonElement>("button[type='submit']") };
  }
  const FM = radioRow(1, "kenwood-tnc2");
  const HF = radioRow(2, "mercury");

  it("has no row with one radio that can send, and Post is off while that radio is not connected, with the reason Send has; on again once it is", async () => {
    const one = on({}, { ...FM, state: "waiting" }, radioRow(3, "lora-console"));
    expect(one.sendOn().exists()).toBe(false);
    await one.wrapper.find("#post-text").setValue("Net tonight 20 UTC");
    expect(one.post().element.disabled).toBe(true);
    expect(one.post().attributes("title")).toBe("FM: not connected");
    await one.wrapper.find("form").trigger("submit");
    expect(one.wrapper.emitted("post")).toBeUndefined();
    await tell(one.daemon, { radios: radiosTopic(FM) });
    expect(one.post().element.disabled).toBe(false);
    expect(one.post().attributes("title")).toBeUndefined();
    await one.wrapper.find("form").trigger("submit");
    expect(one.wrapper.emitted("post")).toEqual([["BLN1", "Net tonight 20 UTC"]]);
  });

  it("has a tick for each radio that can send while several are, under the text, ticked as the bulletin posted last; Post goes while one ticked is connected and sends the ticks", async () => {
    const two = on({ status: status({ new_bulletin_radios: [2] }) }, FM, { ...HF, state: "connecting" });
    expect(two.sendOn().find(".field-label").text()).toBe("Send on");
    expect(two.wrapper.findAll(".composebar-fields > .field").at(-1)?.element).toBe(two.sendOn().element);
    expect(two.ticks()).toEqual([
      ["FM", false, false],
      ["Mercury", true, true],
    ]);
    await two.wrapper.find("#post-text").setValue("Net tonight 20 UTC");
    expect(two.post().element.disabled).toBe(true);
    expect(two.post().attributes("title")).toBe("Mercury: not connected");
    await two.tick("FM");
    expect(two.ticks()).toEqual([
      ["FM", true, false],
      ["Mercury", true, false],
    ]);
    expect(two.post().element.disabled).toBe(false);
    await two.wrapper.find("form").trigger("submit");
    expect(two.wrapper.emitted("post")).toEqual([["BLN1", "Net tonight 20 UTC", [1, 2]]]);
    await answer(two.wrapper, "BLN1", "Net tonight 20 UTC");
    await two.tick("Mercury");
    await two.wrapper.find("#post-text").setValue("Net moved to 21 UTC");
    await two.wrapper.find("form").trigger("submit");
    expect(two.wrapper.emitted("post")?.at(-1)).toEqual(["BLN1", "Net moved to 21 UTC", [1]]);
  });

  it("replaces the ticks of a slot that holds a text of ours with the draft's, as it replaces the text", async () => {
    const two = on({ status: status({ new_bulletin_radios: [1] }) }, FM, HF);
    await two.wrapper.setProps({ ownBulletins: new Map([["BLN1", ownBulletin("BLN1", { radios: [2] })]]) });
    expect(two.ticks()).toEqual([
      ["FM", true, true],
      ["Mercury", false, false],
    ]);
    await two.wrapper.find("#post-text").setValue("Road open again");
    await two.wrapper.find("form").trigger("submit");
    expect(two.wrapper.emitted("post")).toEqual([["BLN1", "Road open again", [1]]]);
  });

  it("shows no tick ticked and none greyed while none of the radios it starts with is on, and Post is off until one is ticked", async () => {
    const three = on({ status: status({ new_bulletin_radios: [3] }) }, FM, HF, radioRow(3, "kiss", { number: 2, enabled: false }));
    await three.wrapper.find("#post-text").setValue("Net tonight");
    expect(three.ticks()).toEqual([
      ["FM", false, false],
      ["Mercury", false, false],
    ]);
    expect(three.post().element.disabled).toBe(true);
    await three.wrapper.find("form").trigger("submit");
    expect(three.wrapper.emitted("post")).toBeUndefined();
    await three.tick("Mercury");
    expect(three.post().element.disabled).toBe(false);
    await three.wrapper.find("form").trigger("submit");
    expect(three.wrapper.emitted("post")).toEqual([["BLN1", "Net tonight", [2]]]);
  });

  it("keeps its rows, the counter and Post where they were when a second radio comes on (in Settings): the row of ticks is added under the text, inside the fields, and the foot stays the box's last line", async () => {
    const station = on({ status: status({ new_bulletin_radios: [1] }) }, FM, { ...HF, enabled: false });
    const fields = () => station.wrapper.findAll(".composebar-fields > .field").map((row) => row.element);
    const before = fields();
    const foot = station.wrapper.find(".composebar-foot").element;
    expect(before).toHaveLength(4);
    await tell(station.daemon, { radios: radiosTopic(FM, HF) });
    expect(fields().slice(0, 4)).toEqual(before); // (the very rows, none made again)
    expect(fields()).toHaveLength(5);
    expect(station.wrapper.find(".composebar-foot").element).toBe(foot);
    expect(foot.previousElementSibling?.classList.contains("composebar-fields")).toBe(true);
    expect(foot.querySelector(".compose-left")).not.toBeNull();
    expect(foot.lastElementChild).toBe(station.post().element);
  });

  it("is off with the daemon's own words while no radio is on, and RX only says its own first", async () => {
    const none = on({ status: status({ unheard_radio: null }) }, { ...FM, enabled: false, state: "stopped" });
    await none.wrapper.find("#post-text").setValue("Net tonight");
    expect(none.post().element.disabled).toBe(true);
    expect(none.post().attributes("title")).toBe("there is no radio: add one, or turn one on");
    const rx = on({ receiveOnly: true }, { ...FM, state: "waiting" });
    await rx.wrapper.find("#post-text").setValue("Net tonight");
    expect(rx.post().attributes("title")).toBe("RX only: nothing is sent");
  });
});

describe("a post in flight", () => {
  it("is posted once for two submits before the daemon has it, and again once it has", async () => {
    const { wrapper, text, post } = compose();
    await text.setValue("Road closed");
    await wrapper.find("form").trigger("submit");
    expect(post.element.disabled).toBe(true);
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")).toHaveLength(1);
    await answer(wrapper, "BLN1", "Road closed");
    await text.setValue("Road open");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")).toHaveLength(2);
  });
});
