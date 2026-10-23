import "@/test/mockmap";
import { describe, expect, it } from "vitest";
import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { type FakeSocket } from "@/test/fakesocket";
import { incoming, message, station } from "@/test/fixtures";
import { open, tabButton, useAppHarness } from "@/test/app";

useAppHarness();

describe("App: the Email tab", () => {
  describe("the Email tab", () => {
    const gateway = (id: number, extra = {}) => incoming(id, "EMAIL-2", { text: "Msg sent to jane@example.com", ...extra });
    const say = async (socket: ReturnType<typeof FakeSocket.last>, rev: number, ...rows: ReturnType<typeof incoming>[]) => {
      socket.say({ type: "patch", topic: "messages", rev, ops: rows.map((r) => ({ op: "set", key: String(r.id), value: r })) });
      await flushPromises();
    };
    const badge = (wrapper: VueWrapper) => tabButton(wrapper, "Email")?.find(".badge");

    it("sends mail as a message to EMAIL-2 from the box that is always there, and Check email as the text get, and keeps the address in the list", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Email")?.trigger("click");
      const pane = () => wrapper.find("#pane-email");
      await wrapper.find("#mail-to").setValue("jane@example.com");
      await wrapper.find("#mail-text").setValue("Hello");
      await pane().find("form.composebar").trigger("submit");
      expect(socket.sent).toContainEqual({ cmd: "send_message", to: "EMAIL-2", text: "jane@example.com Hello" });
      expect(JSON.stringify(socket.sent)).not.toContain("_attempts");
      expect(pane().find("form.composebar").exists()).toBe(true);
      expect(JSON.parse(localStorage.getItem("NeoAPRS.emailto") ?? "[]")).toEqual(["jane@example.com"]);
      await pane()
        .findAll("button")
        .find((b) => b.text() === "Check email")
        ?.trigger("click");
      expect(socket.sent.slice(-2)).toEqual([
        { cmd: "send_message", to: "EMAIL-2", text: "jane@example.com Hello" },
        { cmd: "send_message", to: "EMAIL-2", text: "get" },
      ]);
    });

    it("deletes a row of the list on the daemon after a second press", async () => {
      const { wrapper, socket } = await open();
      await say(socket, 1, message(10, { to_call: "EMAIL-2", text: "me hello" }));
      await tabButton(wrapper, "Email")?.trigger("click");
      await wrapper.find("#pane-email .mail-delete").trigger("click");
      expect(JSON.stringify(socket.sent)).not.toContain("message_delete");
      await wrapper.find("#pane-email .mail-delete").trigger("click");
      expect(socket.sent).toContainEqual({ cmd: "message_delete", id: 10 });
    });

    it("has no attempts field in the Email tab or in the Messages header: the daemon decides", async () => {
      const { wrapper } = await open();
      await tabButton(wrapper, "Email")?.trigger("click");
      expect(wrapper.find("#pane-email .attempts-input").exists()).toBe(false);
      expect(wrapper.find("#pane-messages .attempts-input").exists()).toBe(false);
      expect(wrapper.find("#pane-email").text()).not.toContain("Attempts");
    });

    it("shows the thread with the gateway there and leaves it out of the Messages tab and its count", async () => {
      const { wrapper, socket } = await open();
      await say(socket, 1, message(10, { to_call: "EMAIL-2", text: "me hello" }), gateway(11));
      expect(wrapper.findAll("#pane-email .mail").map((m) => m.find(".mail-title").text())).toEqual(["To me", "From EMAIL-2"]);
      expect(wrapper.findAll("#pane-messages .conv-call").map((c) => c.text())).toEqual(["OH2PU-9", "OH2RDG"]);
      expect(tabButton(wrapper, "Messages")?.find(".badge").text()).toBe("2");
      expect(wrapper.find(".headmail").text()).toContain("3"); // the messages not seen, the gateway's one included: the count of the title and of the folded panel's handle too
    });

    it("shows what came in while the tab was away in bold until the tab is left again", async () => {
      const { wrapper, socket } = await open();
      await say(socket, 1, gateway(11));
      await tabButton(wrapper, "Email")?.trigger("click");
      expect(wrapper.find("#pane-email .mail").classes()).toContain("fresh");
      await say(socket, 2, gateway(12));
      expect(wrapper.findAll("#pane-email .mail.fresh")).toHaveLength(2);
      await tabButton(wrapper, "Stations")?.trigger("click");
      await tabButton(wrapper, "Email")?.trigger("click");
      expect(wrapper.findAll("#pane-email .mail.fresh")).toHaveLength(0);
    });

    it("counts the gateway's messages on the Email tab, in the title and on the folded handle, until the tab is on show", async () => {
      const { wrapper, socket } = await open();
      expect(badge(wrapper)?.exists()).toBe(false);
      await say(socket, 1, gateway(11), gateway(12));
      expect(badge(wrapper)?.text()).toBe("2");
      expect(badge(wrapper)?.attributes("title")).toBe("2 messages not seen yet");
      expect(document.title).toBe("(4) NeoAPRS");
      await wrapper.find(".panel-fold").trigger("click");
      expect(wrapper.find(".fold-badge").text()).toBe("4");
      await wrapper.find(".panel-fold").trigger("click");
      await tabButton(wrapper, "Email")?.trigger("click");
      expect(badge(wrapper)?.exists()).toBe(false);
      expect(document.title).toBe("(2) NeoAPRS");
    });

    it("has one count of the messages not seen: the header, the folded handle and the title say the same", async () => {
      const { wrapper, socket } = await open();
      await say(socket, 1, gateway(11), gateway(12));
      expect(wrapper.find(".headmail").text()).toContain("4");
      expect(document.title).toBe("(4) NeoAPRS");
      await wrapper.find(".panel-fold").trigger("click");
      expect(wrapper.find(".fold-badge").text()).toBe("4");
      expect(wrapper.find(".fold-badge").attributes("title")).toBe("4 messages not seen yet");
    });

    it("opens the Email tab from the header when the messages not seen are all the gateway's", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Messages")?.trigger("click");
      for (const conv of wrapper.findAll("#pane-messages .conv")) await conv.trigger("click");
      await say(socket, 1, gateway(11));
      expect(wrapper.find(".headmail").text()).toContain("1");
      await tabButton(wrapper, "Packets")?.trigger("click");
      await wrapper.find(".headmail").trigger("click");
      expect(wrapper.find("[aria-selected='true']").text()).toContain("Email");
    });

    it("keeps counting while the page is hidden or the panel folded, with the Email tab in front", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Email")?.trigger("click");
      Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "hidden" });
      document.dispatchEvent(new Event("visibilitychange"));
      await say(socket, 1, gateway(11));
      expect(badge(wrapper)?.text()).toBe("1");
      Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "visible" });
      document.dispatchEvent(new Event("visibilitychange"));
      await flushPromises();
      expect(badge(wrapper)?.exists()).toBe(false);
      await wrapper.find(".panel-fold").trigger("click");
      await say(socket, 2, gateway(12));
      expect(wrapper.find(".fold-badge").text()).toBe("3");
    });

    it("is opened by the Message button of the gateway's station card", async () => {
      const { wrapper, socket } = await open();
      socket.say({ type: "patch", topic: "stations", rev: 1, ops: [{ op: "set", key: "EMAIL-2", value: station("EMAIL-2", { lat: null, lon: null }) }] });
      await flushPromises();
      await wrapper
        .findAll("#pane-stations tbody tr")
        .find((r) => r.text().includes("EMAIL-2"))
        ?.trigger("click");
      await wrapper
        .findAll(".card .btn")
        .find((b) => b.text() === "Message")
        ?.trigger("click");
      expect(wrapper.find("[aria-selected='true']").text()).toContain("Email");
    });
  });
});
