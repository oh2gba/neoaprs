import "@/test/mockmap";
import { describe, expect, it } from "vitest";
import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { type FakeSocket } from "@/test/fakesocket";
import { ago, bulletin, errorOf, ownBulletin } from "@/test/fixtures";
import { open, tabButton, useAppHarness } from "@/test/app";

useAppHarness();

describe("App: the Bulletins tab", () => {
  describe("the Bulletins tab", () => {
    const board = {
      "OH2XYZ/BLN1": bulletin("BLN1", { first_heard: ago(600), last_heard: ago(300), times_heard: 3, text: "Road closed" }),
      "OH2ABC/QST": bulletin("QST", { sender: "OH2ABC", kind: "group", first_heard: ago(100), last_heard: ago(100), text: "Club news" }),
    };
    const sayBoard = async (socket: ReturnType<typeof FakeSocket.last>) => {
      socket.say({ type: "state", topic: "bulletins", rev: 0, value: board });
      await flushPromises();
    };
    const badge = (wrapper: VueWrapper) => tabButton(wrapper, "Bulletins")?.find(".badge");

    it("comes after Email and shows the board, with a badge of what is new until it has been on show", async () => {
      const { wrapper, socket } = await open();
      expect(wrapper.findAll("[role='tab']").map((t) => t.text().replace(/\s*\d+$/, ""))).toEqual([
        "Messages",
        "Stations",
        "Email",
        "Bulletins",
        "Objects",
        "Beacon",
        "Packets",
        "Settings",
      ]);
      await sayBoard(socket);
      expect(badge(wrapper)?.text()).toBe("2");
      expect(badge(wrapper)?.attributes("title")).toBe("2 new bulletins");
      await tabButton(wrapper, "Bulletins")?.trigger("click");
      expect(badge(wrapper)?.exists()).toBeFalsy();
      expect(wrapper.findAll("#pane-bulletins .bulletin-text").map((t) => t.text())).toEqual(["Road closed", "Club news"]);
      expect(wrapper.findAll("#pane-bulletins .board-title").map((t) => t.text())).toEqual(["Bulletins 1", "Group messages 1"]);
    });

    it("counts a bulletin that comes while another tab is on show, on the handle of the folded panel too, and not one that comes while it is looked at", async () => {
      const { wrapper, socket } = await open();
      await sayBoard(socket);
      await tabButton(wrapper, "Bulletins")?.trigger("click");
      socket.say({
        type: "patch",
        topic: "bulletins",
        rev: 1,
        ops: [{ op: "set", key: "OH2DEF/BLN2", value: bulletin("BLN2", { sender: "OH2DEF", first_heard: ago(5) }) }],
      });
      await flushPromises();
      expect(badge(wrapper)?.exists()).toBeFalsy();
      await tabButton(wrapper, "Stations")?.trigger("click");
      socket.say({
        type: "patch",
        topic: "bulletins",
        rev: 2,
        ops: [{ op: "set", key: "OH2GHI/BLN3", value: bulletin("BLN3", { sender: "OH2GHI", first_heard: ago(2) }) }],
      });
      await flushPromises();
      expect(badge(wrapper)?.text()).toBe("1");
      await wrapper.find(".panel-fold").trigger("click");
      // the handle counts the messages not seen, as the header does: a new bulletin is not one
      expect(wrapper.find(".fold-badge").text()).toBe("2");
      expect(wrapper.find(".fold-badge").attributes("title")).toBe("2 messages not seen yet");
      expect(wrapper.find(".headmail").text()).toContain("2");
    });

    it("deletes a board entry after two presses of its x, with one command", async () => {
      const { wrapper, socket } = await open();
      await sayBoard(socket);
      await tabButton(wrapper, "Bulletins")?.trigger("click");
      const x = () => wrapper.find("#pane-bulletins .bulletin-delete");
      await x().trigger("click");
      expect(x().text()).toBe("sure?");
      expect(JSON.stringify(socket.sent)).not.toContain("bulletin_delete");
      await x().trigger("click");
      expect(socket.sent.filter((c) => (c as { cmd?: string }).cmd === "bulletin_delete")).toHaveLength(1);
    });

    it("forgets a bulletin that was deleted", async () => {
      const { wrapper, socket } = await open();
      await sayBoard(socket);
      await tabButton(wrapper, "Bulletins")?.trigger("click");
      socket.say({ type: "patch", topic: "bulletins", rev: 1, ops: [{ op: "del", key: "OH2XYZ/BLN1" }] });
      await flushPromises();
      expect(wrapper.findAll("#pane-bulletins .bulletin")).toHaveLength(1);
    });
  });

  describe("posting to the board", () => {
    it("posts a bulletin from the box on the Bulletins tab, with one command, and shows ours on the board when the daemon says so", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Bulletins")?.trigger("click");
      await wrapper.find("#post-text").setValue("Road closed");
      await wrapper.find("#pane-bulletins .bulletin-compose").trigger("submit");
      expect(socket.sent.filter((c) => (c as { cmd?: string }).cmd === "bulletin_post")).toEqual([{ cmd: "bulletin_post", slot: "BLN1", text: "Road closed" }]);
      expect(wrapper.find<HTMLInputElement>("#post-text").element.value).toBe("Road closed");
      socket.say(errorOf("bulletin_post: set your call first"));
      await flushPromises();
      expect(wrapper.find<HTMLInputElement>("#post-text").element.value).toBe("Road closed");
      socket.say({ type: "state", topic: "own_bulletins", rev: 0, value: { BLN1: ownBulletin("BLN1", { text: "Road closed" }) } });
      await flushPromises();
      expect(wrapper.find<HTMLInputElement>("#post-text").element.value).toBe("");
      const mine = wrapper.find("#pane-bulletins .bulletin.mine");
      expect(mine.find(".bulletin-head strong").text()).toBe("OH2GBA");
      expect(mine.find(".own-mark").text()).toBe("ours");
      expect(mine.find(".bulletin-text").text()).toBe("Road closed");
    });

    it("stops one of ours after two presses of its x, with one command, and the board forgets it when the daemon deletes it", async () => {
      const { wrapper, socket } = await open();
      socket.say({ type: "state", topic: "own_bulletins", rev: 0, value: { BLN1: ownBulletin("BLN1") } });
      await flushPromises();
      await tabButton(wrapper, "Bulletins")?.trigger("click");
      const x = () => wrapper.find("#pane-bulletins .mine .bulletin-delete");
      await x().trigger("click");
      await x().trigger("click");
      expect(socket.sent.filter((c) => (c as { cmd?: string }).cmd === "bulletin_unpost")).toEqual([{ cmd: "bulletin_unpost", slot: "BLN1" }]);
      expect(socket.sent.filter((c) => (c as { cmd?: string }).cmd === "bulletin_delete")).toEqual([]);
      socket.say({ type: "patch", topic: "own_bulletins", rev: 1, ops: [{ op: "del", key: "BLN1" }] });
      await flushPromises();
      expect(wrapper.find("#pane-bulletins .mine").exists()).toBe(false);
    });
  });
});
