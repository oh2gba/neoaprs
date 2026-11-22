import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { LIMITS } from "@/protocol/lists";
import type { OwnBulletinRow, RadioRow } from "@/protocol/protocol";
import { fakeDaemon, ofRadios, tell, withDaemon, type Given } from "@/test/context";
import { cssRule } from "@/test/css";
import { ownBulletin, radioRow, radiosTopic, status, toastOf } from "@/test/fixtures";
import { shown } from "@/test/shown";
import BulletinCompose from "@/components/BulletinCompose.vue";

/** The command a post sends: the kind, the text and the hours (the group and the radios when given). */
const cmd = (kind: string, text: string, hours = 4, extra: Record<string, unknown> = {}) => [
  { cmd: "bulletin_post", kind, text, hours, ...extra },
];

/** The daemon has the post: its row is told, beside `others` of ours. */
const answer = (
  wrapper: { setProps: (props: { ownBulletins: Map<string, OwnBulletinRow> }) => Promise<void> },
  slot: string,
  text: string,
  extra: Partial<OwnBulletinRow> = {},
  others: [string, OwnBulletinRow][] = [],
) => wrapper.setProps({ ownBulletins: new Map([...others, [slot, ownBulletin(slot, { text, ...extra })]]) });

/** Ours in every slot of these. */
const ours = (...slots: string[]) => new Map(slots.map((slot) => [slot, ownBulletin(slot, { next_at: null })]));
const DIGITS = [..."0123456789"].map((c) => `BLN${c}`);

function compose(given?: Given) {
  const daemon = given === undefined ? undefined : fakeDaemon(given);
  const wrapper = mount(BulletinCompose, {
    props: { ownBulletins: new Map<string, OwnBulletinRow>() },
    ...(daemon === undefined ? {} : { global: withDaemon(daemon) }),
  });
  const kind = wrapper.find<HTMLSelectElement>("#post-kind");
  const sentFor = wrapper.find<HTMLSelectElement>("#post-sent-for");
  const text = wrapper.find<HTMLInputElement>("#post-text");
  const group = wrapper.find<HTMLInputElement>("#post-group");
  const post = wrapper.find<HTMLButtonElement>("button[type='submit']");
  const choices = () => sentFor.findAll("option").map((o) => o.text());
  return { wrapper, daemon, kind, sentFor, choices, group, text, post };
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
  it("names the three kinds only, with no time in them", () => {
    const { kind } = compose();
    expect(kind.findAll("option").map((o) => [o.element.value, o.text()])).toEqual([
      ["bulletin", "Bulletin"],
      ["announcement", "Announcement"],
      ["group", "Group bulletin"],
    ]);
    expect(kind.element.value).toBe("bulletin");
  });

  it("has a kind, Sent for, the group, the text and Post, no number or letter and no Replace, and no line of help under a field", () => {
    const { wrapper, group, post } = compose();
    expect(rows(wrapper)).toEqual([
      { label: "Kind", control: "post-kind", greyed: false },
      { label: "Sent for", control: "post-sent-for", greyed: false },
      { label: "Group", control: "post-group", greyed: true },
      { label: "Text", control: "post-text", greyed: false },
    ]);
    expect(wrapper.find("#post-id").exists()).toBe(false);
    expect(group.element.disabled).toBe(true);
    expect(shown(post)).toBe("Post");
    expect(wrapper.text()).not.toMatch(/Replace|Number|Letter/);
    expect(wrapper.find(".twowords").exists()).toBe(false);
    expect(wrapper.find("p").exists()).toBe(false);
  });

  it("offers the daemon's Sent for choices of the kind, hours for a bulletin and a group bulletin and days for an announcement", async () => {
    const { kind, sentFor, choices } = compose();
    expect(LIMITS.bulletin.hours).toEqual([1, 2, 4, 8, 12]);
    expect(choices()).toEqual(["1 hour", "2 hours", "4 hours", "8 hours", "12 hours"]);
    expect(sentFor.element.value).toBe("4");
    await kind.setValue("announcement");
    expect(choices()).toEqual(["1 day", "3 days", "7 days"]);
    expect(sentFor.element.value).toBe("72");
    await kind.setValue("group");
    expect(choices()).toEqual(["1 hour", "2 hours", "4 hours", "8 hours", "12 hours"]);
    expect(sentFor.element.value).toBe("4");
  });

  it("starts Sent for at the station's choice for the kind, also when the status comes late, and keeps a choice made until the kind changes", async () => {
    const { daemon, kind, sentFor, text, wrapper } = compose({});
    expect(sentFor.element.value).toBe("4");
    await tell(daemon!, { status: status({ new_bulletin_hours: { bulletin: 8, announcement: 168, group: 2 } }) });
    expect(sentFor.element.value, "the status came after the box").toBe("8");
    await sentFor.setValue("12");
    await tell(daemon!, { status: status({ new_bulletin_hours: { bulletin: 1, announcement: 168, group: 2 } }) });
    expect(sentFor.element.value, "a status does not undo a choice").toBe("12");
    await kind.setValue("announcement");
    expect(sentFor.element.value).toBe("168");
    await kind.setValue("group");
    expect(sentFor.element.value).toBe("2");
    await kind.setValue("bulletin");
    expect(sentFor.element.value, "a kind change drops the choice").toBe("1");
    await sentFor.setValue("8");
    await text.setValue("Net tonight");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")).toEqual([cmd("bulletin", "Net tonight", 8)]);
  });

  it("has an (i) at the end of each of the four rows, named after the row, with no title", () => {
    const { wrapper } = compose();
    const toggles = wrapper
      .findAll(".composebar-fields > .field")
      .map((row) => row.find(".field-control .info-toggle"));
    expect(toggles.map((t) => t.attributes("aria-label"))).toEqual([
      "About Kind",
      "About Sent for",
      "About Group",
      "About Text",
    ]);
    expect(toggles.map((t) => t.attributes("title"))).toEqual([undefined, undefined, undefined, undefined]);
  });

  it("explains each row in at most two lines, Sent for in one, and the kind's and the group's notes have their pictures", async () => {
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
    expect(kind.lines.join(" ")).not.toMatch(/\d/);
    const sentFor = await open("Sent for");
    expect(sentFor.lines).toEqual(["How long the post is repeated, counted from its first packet."]);
    const group = await open("Group");
    expect(group.picture).toBe("bulletingroup");
    expect(group.lines).toHaveLength(2);
    expect(group.lines.join(" ")).toContain("part of the address");
    const text = await open("Text");
    expect(text.lines).toHaveLength(2);
    expect(text.lines[0]).toContain(`${LIMITS.message.textMax} characters`);
    expect(text.lines[1]).toContain("Sent for");
  });

  it("moves nothing when the kind changes: the same four rows in the same places, Sent for as Kind is, the group's greyed unless it is a group bulletin", async () => {
    const { wrapper, kind, sentFor, group, text } = compose();
    const places = () => wrapper.findAll(".composebar-fields > .field").map((row) => row.element);
    const form = wrapper.element as HTMLElement;
    const controls = () =>
      [kind.element, sentFor.element, group.element, text.element].map((control) => form.contains(control));
    const before = places();
    const seen: Record<string, ReturnType<typeof rows>> = {};
    for (const value of ["announcement", "group", "bulletin"]) {
      await kind.setValue(value);
      expect(
        places().map((row, at) => row === before[at]),
        value,
      ).toEqual([true, true, true, true]); // (the very rows: none added, none taken out, none made again)
      expect(controls(), value).toEqual([true, true, true, true]);
      expect(sentFor.element, value).toBe(wrapper.find("#post-sent-for").element);
      seen[value] = rows(wrapper);
    }
    expect(seen["announcement"]?.map((r) => [r.label, r.greyed])).toEqual([
      ["Kind", false],
      ["Sent for", false],
      ["Group", true],
      ["Text", false],
    ]);
    expect(seen["group"]?.map((r) => [r.label, r.greyed])).toEqual([
      ["Kind", false],
      ["Sent for", false],
      ["Group", false],
      ["Text", false],
    ]);
    expect(group.element.disabled).toBe(true);
    // Sent for is as wide as its row whatever its options say (hours or days), as Kind is: the same
    // class, no width or size of its own, in the row's control
    expect(sentFor.classes()).toEqual(kind.classes());
    expect(sentFor.attributes("style")).toBeUndefined();
    expect(sentFor.attributes("size")).toBeUndefined();
    expect(sentFor.element.parentElement?.classList.contains("field-control")).toBe(true);
    expect(cssRule(".field-control .input")).toMatch(/flex:\s*1/);
    for (const selector of [".input", ".field-control", "fieldset.composebox"])
      expect(cssRule(selector), selector).toMatch(/min-width:\s*0/);
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
    expect(wrapper.emitted("post")).toEqual([cmd("bulletin", "Road closed")]);
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

  it("has Post off, with no title and nothing red, while every number of the kind holds a post of ours, an ended one too; on for another kind or group", async () => {
    const { wrapper, kind, group, text, post } = compose();
    await text.setValue("Net tonight");
    await wrapper.setProps({ ownBulletins: ours(...DIGITS) });
    expect(post.element.disabled).toBe(true);
    expect(post.attributes("title")).toBeUndefined();
    expect(shown(post)).toBe("Post");
    await kind.setValue("announcement");
    expect(post.element.disabled).toBe(false);
    await kind.setValue("group");
    await wrapper.setProps({ ownBulletins: ours(...DIGITS.map((slot) => `${slot}HAMS`)) });
    await group.setValue("hams");
    expect(post.element.disabled).toBe(true);
    expect(post.attributes("title")).toBeUndefined();
    expect(wrapper.find(".invalid").exists()).toBe(false);
    await group.setValue("wx");
    expect(post.element.disabled).toBe(false);
  });

  it("has Post off, with no title, while 36 posts of ours are on the board", async () => {
    const { wrapper, text, post } = compose();
    await text.setValue("Net tonight");
    const letters = [..."ABCDEFGHIJKLMNOPQRSTUVWXYZ"].map((c) => `BLN${c}`);
    await wrapper.setProps({ ownBulletins: ours(...DIGITS.slice(0, 9), ...letters, "BLN0HAMS") });
    expect(post.element.disabled).toBe(true);
    expect(post.attributes("title")).toBeUndefined();
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

  it("posts the kind, the text and Sent for, and keeps them until the daemon has the post in a new slot, then empties the text and keeps the kind", async () => {
    const { wrapper, kind, sentFor, text } = compose();
    await kind.setValue("announcement");
    await sentFor.setValue("168");
    await text.setValue(" Club meeting ");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")).toEqual([cmd("announcement", "Club meeting", 168)]);
    expect(text.element.value).toBe(" Club meeting ");
    await answer(wrapper, "BLNA", "Club meeting", { kind: "announcement" });
    expect(text.element.value).toBe("");
    expect(kind.element.value).toBe("announcement");
  });

  it("keeps the text when the daemon refuses, and a post of ours that was there before is not the answer", async () => {
    const { wrapper, daemon, text } = compose({});
    const before = ownBulletin("BLN0", { text: "Road closed" });
    await wrapper.setProps({ ownBulletins: new Map([["BLN0", before]]) });
    await text.setValue("Road closed");
    await wrapper.find("form").trigger("submit");
    await wrapper.setProps({ ownBulletins: new Map([["BLN0", { ...before, sent: 3 }]]) });
    expect(text.element.value, "the one before, sent again").toBe("Road closed");
    await tell(daemon!, { lastError: toastOf("bulletin_post: no call", "other") });
    expect(text.element.value).toBe("Road closed");
    await text.setValue("Road open");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")).toEqual([cmd("bulletin", "Road closed"), cmd("bulletin", "Road open")]);
    await answer(wrapper, "BLN1", "Road open", {}, [["BLN0", before]]);
    expect(text.element.value).toBe("");
  });

  it("takes a new row of another kind or group with the same text for no answer, and leaves what was typed since", async () => {
    const { wrapper, kind, group, text } = compose();
    await kind.setValue("group");
    await group.setValue("hams");
    await text.setValue("same");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")).toEqual([cmd("group", "same", 4, { group: "HAMS" })]);
    await answer(wrapper, "BLN0WX", "same", { kind: "group", group: "WX" });
    expect(text.element.value).toBe("same");
    await text.setValue("typed meanwhile");
    await answer(wrapper, "BLN0HAMS", "same", { kind: "group", group: "HAMS" });
    expect(text.element.value).toBe("typed meanwhile");
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
    expect(wrapper.emitted("post")).toEqual([cmd("group", "Net tonight 20:00", 4, { group: "HAMS" })]);
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
    const wrapper = mount(BulletinCompose, {
      props: { ownBulletins: new Map<string, OwnBulletinRow>() },
      global: withDaemon(daemon),
    });
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
    return {
      wrapper,
      daemon,
      sendOn,
      ticks,
      tick,
      post: () => wrapper.find<HTMLButtonElement>("button[type='submit']"),
    };
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
    expect(one.wrapper.emitted("post")).toEqual([cmd("bulletin", "Net tonight 20 UTC")]);
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
    expect(two.wrapper.emitted("post")).toEqual([cmd("bulletin", "Net tonight 20 UTC", 4, { radios: [1, 2] })]);
    await answer(two.wrapper, "BLN0", "Net tonight 20 UTC");
    await two.tick("Mercury");
    await two.wrapper.find("#post-text").setValue("Net moved to 21 UTC");
    await two.wrapper.find("form").trigger("submit");
    expect(two.wrapper.emitted("post")?.at(-1)).toEqual(cmd("bulletin", "Net moved to 21 UTC", 4, { radios: [1] }));
  });

  it("starts the ticks as the station's, whatever the radios of a post of ours already on the board", async () => {
    const two = on({ status: status({ new_bulletin_radios: [1] }) }, FM, HF);
    await two.wrapper.setProps({ ownBulletins: new Map([["BLN0", ownBulletin("BLN0", { radios: [2] })]]) });
    expect(two.ticks()).toEqual([
      ["FM", true, true],
      ["Mercury", false, false],
    ]);
    await two.wrapper.find("#post-text").setValue("Road open again");
    await two.wrapper.find("form").trigger("submit");
    expect(two.wrapper.emitted("post")).toEqual([cmd("bulletin", "Road open again", 4, { radios: [1] })]);
  });

  it("shows no tick ticked and none greyed while none of the radios it starts with is on, and Post is off until one is ticked", async () => {
    const three = on(
      { status: status({ new_bulletin_radios: [3] }) },
      FM,
      HF,
      radioRow(3, "kiss", { number: 2, enabled: false }),
    );
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
    expect(three.wrapper.emitted("post")).toEqual([cmd("bulletin", "Net tonight", 4, { radios: [2] })]);
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
    await answer(wrapper, "BLN0", "Road closed");
    await text.setValue("Road open");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")).toHaveLength(2);
  });
});
