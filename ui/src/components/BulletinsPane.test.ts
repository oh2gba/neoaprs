import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import BulletinsPane from "@/components/BulletinsPane.vue";
import type { BulletinRow } from "@/protocol/protocol";
import { NOW, ago, bulletin } from "@/test/fixtures";

const board = (...rows: BulletinRow[]) => new Map(rows.map((r) => [`${r.sender}/${r.slot}`, r]));

function pane(...rows: BulletinRow[]) {
  return mount(BulletinsPane, { props: { bulletins: board(...rows), now: NOW } });
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
});
