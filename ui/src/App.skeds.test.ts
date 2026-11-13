import "@/test/mockmap";
import { describe, expect, it } from "vitest";
import { flushPromises, type VueWrapper } from "@vue/test-utils";
import type { FakeSocket } from "@/test/fakesocket";
import { NOW, sked, skedsState } from "@/test/fixtures";
import { open, tabButton, useAppHarness } from "@/test/app";

useAppHarness();

const at = (hours: number) => new Date(NOW + hours * 3_600_000).toISOString().slice(0, 19) + "Z";
const cmds = (socket: FakeSocket, cmd: string) => socket.sent.filter((c) => (c as { cmd?: string }).cmd === cmd);
const board = [sked("a", { call: "OH2XYZ", note: "Mercury, 10 W" }), sked("b", { call: "OH2ABC", from: at(30), to: at(32) })];
const sayBoard = async (socket: FakeSocket, rows = board) => {
  socket.say({ type: "state", topic: "skeds", rev: 0, value: skedsState(rows) });
  await flushPromises();
};
const badge = (wrapper: VueWrapper) => tabButton(wrapper, "Skeds")?.find(".badge");

describe("App: the Skeds tab", () => {
  it("comes after Bulletins and before Objects", async () => {
    const { wrapper } = await open();
    const names = wrapper.findAll("[role='tab']").map((t) => t.text().replace(/\s*\d+$/, ""));
    expect(names.indexOf("Skeds")).toBe(names.indexOf("Bulletins") + 1);
    expect(names.indexOf("Objects")).toBe(names.indexOf("Skeds") + 1);
  });

  it("carries the count of the skeds not seen until it has been on show, and asks for the board when it comes on show", async () => {
    const { wrapper, socket } = await open();
    await sayBoard(socket);
    expect(badge(wrapper)?.text()).toBe("2");
    expect(badge(wrapper)?.attributes("title")).toBe("2 new skeds");
    expect(cmds(socket, "skeds_wanted")).toEqual([]);
    await tabButton(wrapper, "Skeds")?.trigger("click");
    expect(badge(wrapper)?.exists()).toBeFalsy();
    expect(cmds(socket, "skeds_wanted")).toEqual([{ cmd: "skeds_wanted" }]);
    expect(wrapper.findAll("#pane-skeds .sked")).toHaveLength(2);
  });

  it("counts a sked that comes while another tab is on show, and not one that comes while the board is looked at", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Skeds")?.trigger("click");
    await sayBoard(socket);
    expect(badge(wrapper)?.exists()).toBeFalsy();
    await tabButton(wrapper, "Stations")?.trigger("click");
    await sayBoard(socket, [...board, sked("c", { call: "OH2NEW", from: at(50), to: at(51) })]);
    expect(badge(wrapper)?.text()).toBe("1");
    expect(badge(wrapper)?.attributes("title")).toBe("1 new sked");
  });

  it("posts from the form with one command, and shows ours on the board, with Delete, when the daemon says so", async () => {
    const { wrapper, socket } = await open();
    await sayBoard(socket, []);
    await tabButton(wrapper, "Skeds")?.trigger("click");
    await wrapper.find("#sked-note").setValue("Mercury");
    await wrapper.find("#pane-skeds .sked-compose").trigger("submit");
    expect(cmds(socket, "sked_post")).toEqual([
      { cmd: "sked_post", from: "2026-10-21T12:00:00Z", to: "2026-10-21T13:00:00Z", dial: "7.0541 MHz USB", note: "Mercury" },
    ]);
    expect(wrapper.find<HTMLInputElement>("#sked-note").element.value).toBe("Mercury");
    await sayBoard(socket, [sked("m", { call: "OH2GBA", ours: true, from: "2026-10-21T12:00:00Z", to: "2026-10-21T13:00:00Z", note: "Mercury" })]);
    expect(wrapper.find<HTMLInputElement>("#sked-note").element.value).toBe("");
    const mine = wrapper.find("#pane-skeds .sked.mine");
    expect(mine.find(".sked-call").text()).toContain("OH2GBA");
    expect(mine.find(".sked-when .muted").text()).toBe("now");
    await mine.find(".xbtn").trigger("click");
    await mine.find(".xbtn").trigger("click");
    expect(cmds(socket, "sked_delete")).toEqual([{ cmd: "sked_delete", id: "m" }]);
  });

  it("joins the sked of another station with one command", async () => {
    const { wrapper, socket } = await open();
    await sayBoard(socket);
    await tabButton(wrapper, "Skeds")?.trigger("click");
    await wrapper.find("#pane-skeds .sked-actions .btn").trigger("click");
    expect(cmds(socket, "sked_post")).toEqual([{ cmd: "sked_post", from: at(2), to: at(4), dial: "7.0541 MHz USB", note: "" }]);
  });

  it("shows the board without the form for a closed board, and says nothing for one that cannot be reached", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Skeds")?.trigger("click");
    socket.say({ type: "state", topic: "skeds", rev: 0, value: skedsState(board, { state: "closed" }) });
    await flushPromises();
    expect(wrapper.find("#pane-skeds form").exists()).toBe(false);
    expect(wrapper.findAll("#pane-skeds .sked")).toHaveLength(2);
    socket.say({ type: "state", topic: "skeds", rev: 1, value: skedsState(board, { state: "offline" }) });
    await flushPromises();
    expect(wrapper.find("#pane-skeds form").exists()).toBe(true);
    expect(wrapper.find("#pane-skeds button[type='submit']").attributes("disabled")).toBeDefined();
    expect(wrapper.find("#pane-skeds").text()).not.toMatch(/offline|reach|unavailable/i);
  });
});
