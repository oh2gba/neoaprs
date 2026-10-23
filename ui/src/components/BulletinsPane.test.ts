import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import BulletinsPane from "@/components/BulletinsPane.vue";
import type { BulletinRow, OwnBulletinRow } from "@/protocol/protocol";
import { NOW, ago, bulletin, ownBulletin } from "@/test/fixtures";

const board = (...rows: BulletinRow[]) => new Map(rows.map((r) => [`${r.sender}/${r.slot}`, r]));

const posted = (...rows: OwnBulletinRow[]) => new Map(rows.map((r) => [r.slot, r]));

function pane(...rows: BulletinRow[]) {
  return mount(BulletinsPane, { props: { bulletins: board(...rows), ownBulletins: new Map<string, OwnBulletinRow>(), call: "OH2GBA", now: NOW } });
}

const rows = [
  bulletin("BLN1", { text: "Road closed at Kaivopuisto", last_heard: ago(300), times_heard: 3 }),
  bulletin("BLNA", { kind: "announcement", sender: "OH2ABC", text: "Club meeting on Thursday", last_heard: ago(7200) }),
  bulletin("BLN3HAMS", { kind: "group", group: "HAMS", text: "Net tonight 20:00", last_heard: ago(60) }),
  bulletin("QST", { kind: "group", sender: "OH2DEF", text: "Club news", last_heard: ago(30) }),
];

describe("BulletinsPane", () => {
  it("has the three sections in their order, each row newest first", () => {
    const wrapper = pane(...rows);
    expect(wrapper.findAll(".board-title").map((t) => t.text())).toEqual(["Announcements 1", "Bulletins 1", "Group messages 2"]);
    expect(wrapper.findAll(".bulletin-text").map((t) => t.text())).toEqual([
      "Club meeting on Thursday",
      "Road closed at Kaivopuisto",
      "Club news",
      "Net tonight 20:00",
    ]);
  });

  it("shows the weather service bulletins in a section of their own, last", () => {
    const wrapper = pane(...rows, bulletin("NWS-WARN", { kind: "nws", sender: "OH2NWS", text: "Gale warning", last_heard: ago(5) }));
    expect(wrapper.findAll(".board-title").map((t) => t.text())).toEqual(["Announcements 1", "Bulletins 1", "Group messages 2", "Weather service 1"]);
    expect(wrapper.findAll(".bulletin-text").at(-1)?.text()).toBe("Gale warning");
  });

  it("shows for each row who sent it, what it is addressed to (the group, else the slot), how often it was heard and how long ago", () => {
    const wrapper = pane(...rows);
    const [announcement, bulletinRow, qst, group] = wrapper.findAll(".bulletin");
    expect(announcement?.find(".bulletin-head").text()).toBe("OH2ABC to BLNA");
    expect(bulletinRow?.find(".bulletin-head").text()).toBe("OH2XYZ to BLN1");
    expect(qst?.find(".bulletin-head").text()).toBe("OH2DEF to QST");
    expect(group?.find(".bulletin-head").text()).toBe("OH2XYZ to HAMS");
    expect(group?.find(".bulletin-target").attributes("title")).toBe("BLN3HAMS");
    expect(bulletinRow?.find(".bulletin-meta").text()).toBe("heard 3 times, 5 min ago");
    expect(announcement?.find(".bulletin-meta").text()).toBe("heard once, 2 h ago");
  });

  describe("the x of a row", () => {
    const x = (wrapper: ReturnType<typeof pane>, i: number) => wrapper.findAll(".bulletin")[i]?.find(".bulletin-delete");

    it("is a small x at the corner of every row", () => {
      const wrapper = pane(...rows);
      expect(wrapper.findAll(".bulletin-delete").map((b) => b.text())).toEqual(["x", "x", "x", "x"]);
      expect(x(wrapper, 1)?.attributes("aria-label")).toBe("Delete the bulletin BLN1 from OH2XYZ");
      expect(x(wrapper, 0)?.classes()).toContain("conv-delete");
    });

    it("asks twice: the first press says sure?, the second emits the sender and the slot", async () => {
      const wrapper = pane(...rows);
      await x(wrapper, 1)?.trigger("click");
      expect(x(wrapper, 1)?.text()).toBe("sure?");
      expect(x(wrapper, 0)?.text()).toBe("x");
      expect(wrapper.emitted("delete")).toBeUndefined();
      await x(wrapper, 1)?.trigger("click");
      expect(wrapper.emitted("delete")).toEqual([["OH2XYZ", "BLN1"]]);
      expect(x(wrapper, 1)?.text()).toBe("x");
    });

    it("arms one row at a time", async () => {
      const wrapper = pane(...rows);
      await x(wrapper, 0)?.trigger("click");
      await x(wrapper, 1)?.trigger("click");
      expect(wrapper.findAll(".bulletin-delete").map((b) => b.text())).toEqual(["x", "sure?", "x", "x"]);
      expect(wrapper.emitted("delete")).toBeUndefined();
    });
  });

  it("writes the text as text, never as markup", () => {
    const wrapper = pane(bulletin("BLN1", { text: "<b>bold</b> & <script>x</script>" }));
    expect(wrapper.find(".bulletin-text").text()).toBe("<b>bold</b> & <script>x</script>");
    expect(wrapper.find(".bulletin-text b").exists()).toBe(false);
  });

  it("says so when the board is empty, and has no section", () => {
    const wrapper = pane();
    expect(wrapper.find(".empty").text()).toBe("Nothing on the board.");
    expect(wrapper.find(".board-section").exists()).toBe(false);
  });

  it("follows the board: a row heard again and one that was deleted", async () => {
    const wrapper = pane(...rows);
    const next = board(...rows.slice(0, 2), bulletin("BLN1", { text: "Road open again", last_heard: ago(5) }));
    await wrapper.setProps({ bulletins: next });
    expect(wrapper.findAll(".bulletin-text").map((t) => t.text())).toEqual(["Club meeting on Thursday", "Road open again"]);
  });

  it("has the box to post in on top, and passes what is posted on", async () => {
    const wrapper = pane(...rows);
    expect(wrapper.find(".bulletin-compose").exists()).toBe(true);
    await wrapper.find("#post-text").setValue("Hello board");
    await wrapper.find(".bulletin-compose").trigger("submit");
    expect(wrapper.emitted("post")).toEqual([["BLN1", "Hello board"]]);
  });

  describe("our own bulletins", () => {
    const withOurs = (...own: OwnBulletinRow[]) =>
      mount(BulletinsPane, { props: { bulletins: board(...rows), ownBulletins: posted(...own), call: "OH2GBA", now: NOW } });
    const ours = ownBulletin("BLN2", { text: "Gale warning from us", last_sent_at: ago(30), sent: 3 });

    it("are on the board in their section with our call, marked ours, with how often they were sent and when they go out next", () => {
      const wrapper = withOurs(ours);
      const items = wrapper.findAll(".bulletin");
      const mine = items.find((b) => b.classes().includes("mine"));
      expect(items).toHaveLength(5);
      expect(wrapper.findAll(".board-title").map((t) => t.text())).toEqual(["Announcements 1", "Bulletins 2", "Group messages 2"]);
      expect([mine?.find(".bulletin-head strong").text(), mine?.find(".bulletin-target").text()]).toEqual(["OH2GBA", "BLN2"]);
      expect(mine?.find(".own-mark").text()).toBe("ours");
      expect(mine?.find(".bulletin-text").text()).toBe("Gale warning from us");
      expect(mine?.find(".bulletin-meta").text()).toBe("sent 3 times, next in 18 min");
      expect(items.filter((b) => b.classes().includes("mine"))).toHaveLength(1);
      expect(wrapper.findAll(".own-mark")).toHaveLength(1);
    });

    it("say ended when their schedule is over, and not yet sent before the first packet", () => {
      expect(
        withOurs(ownBulletin("BLN2", { sent: 14, next_at: null }))
          .find(".mine .bulletin-meta")
          .text(),
      ).toBe("sent 14 times, ended");
      expect(
        withOurs(ownBulletin("BLN2", { sent: 0, last_sent_at: null, next_at: null }))
          .find(".mine .bulletin-meta")
          .text(),
      ).toBe("not sent yet");
    });

    it("are the call of a group bulletin's group, as the others are", () => {
      const wrapper = withOurs(ownBulletin("BLN3HAMS", { kind: "group", group: "HAMS" }));
      expect(wrapper.find(".mine .bulletin-target").text()).toBe("HAMS");
    });

    it("have an x that asks twice and then stops the bulletin, with its slot, not the delete of a heard one", async () => {
      const wrapper = withOurs(ours);
      const x = () => wrapper.find(".mine .bulletin-delete");
      expect(x().attributes("aria-label")).toBe("Delete our bulletin BLN2");
      await x().trigger("click");
      expect(x().text()).toBe("sure?");
      expect(wrapper.emitted("unpost")).toBeUndefined();
      await x().trigger("click");
      expect(wrapper.emitted("unpost")).toEqual([["BLN2"]]);
      expect(wrapper.emitted("delete")).toBeUndefined();
    });

    it("follow the topic: one that is sent again, one that is gone", async () => {
      const wrapper = withOurs(ours);
      await wrapper.setProps({ ownBulletins: posted(ownBulletin("BLN2", { sent: 4, text: "Gale warning from us" })) });
      expect(wrapper.find(".mine .bulletin-meta").text()).toBe("sent 4 times, next in 18 min");
      await wrapper.setProps({ ownBulletins: posted() });
      expect(wrapper.find(".mine").exists()).toBe(false);
    });

    it("are under a word for our call until the daemon says it", () => {
      const wrapper = mount(BulletinsPane, { props: { bulletins: board(), ownBulletins: posted(ours), call: null, now: NOW } });
      expect(wrapper.find(".mine .bulletin-head strong").text()).toBe("us");
    });
  });
});
