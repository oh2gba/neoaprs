import "@/test/mockmap";
import { describe, expect, it } from "vitest";
import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { incoming, message } from "@/test/fixtures";
import { open, tabButton, useAppHarness } from "@/test/app";

const { setPanelWidth } = useAppHarness();

describe("App: messages", () => {
  it("has the message settings in the conversation the card's Message button opens, none on the card; RF only is sent and follows the daemon", async () => {
    const { wrapper, socket } = await open();
    await wrapper
      .findAll("#pane-stations tbody tr")
      .find((r) => r.text().includes("OH2PU-9"))
      ?.trigger("click");
    expect(wrapper.find(".card .rfonly").exists()).toBe(false);
    expect(wrapper.find(".card .use-suggested").exists()).toBe(false);
    await wrapper
      .findAll(".card .btn")
      .find((b) => b.text() === "Message")
      ?.trigger("click");
    await wrapper.find("#pane-messages .convo-head .route-button").trigger("click");
    const header = wrapper.find<HTMLInputElement>("#pane-messages .route-box .rfonly input");
    expect(wrapper.findAll("#pane-messages .route-box label").map((l) => l.text())).toEqual(["Path", "RF only"]);
    await header.setValue(true);
    expect(socket.sent).toContainEqual({ cmd: "set_station_rf_only", call: "OH2PU-9", on: true });
    socket.say({
      type: "patch",
      topic: "station_prefs",
      rev: 1,
      ops: [{ op: "set", key: "OH2PU-9", value: { path: null, rf_only: true, alert: null } }],
    });
    await flushPromises();
    expect(wrapper.find<HTMLInputElement>("#pane-messages .route-box .rfonly input").element.checked).toBe(true);
    await wrapper.find<HTMLInputElement>("#pane-messages .route-box .rfonly input").setValue(false);
    expect(socket.sent).toContainEqual({ cmd: "set_station_rf_only", call: "OH2PU-9", on: false });
  });

  describe("messages not seen", () => {
    const show = (state: "visible" | "hidden") => {
      Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
      document.dispatchEvent(new Event("visibilitychange"));
    };

    it("counts them in the title of the browser tab, in the header and on the Messages tab", async () => {
      const { wrapper } = await open();
      expect(document.title).toBe("(2) NeoAPRS");
      expect(wrapper.find(".headmail").text()).toContain("2");
      expect(tabButton(wrapper, "Messages")?.find(".badge").text()).toBe("2");
    });

    it("shows the count on the handle of the folded panel, and on no other", async () => {
      const { wrapper } = await open();
      expect(wrapper.find(".fold-badge").exists()).toBe(false);
      await wrapper.find(".panel-fold").trigger("click");
      expect(wrapper.find(".fold-badge").text()).toBe("2");
      await wrapper.find(".panel-fold").trigger("click");
      expect(wrapper.find(".fold-badge").exists()).toBe(false);
    });

    it("opens the Messages tab on the newest conversation with something new from the header, and the title counts down", async () => {
      const { wrapper } = await open();
      await wrapper.find(".panel-fold").trigger("click");
      await wrapper.find(".headmail").trigger("click");
      expect(wrapper.find(".panel").classes()).not.toContain("collapsed");
      expect(wrapper.find("[aria-selected='true']").text()).toContain("Messages");
      expect(wrapper.find(".conv.active .conv-call").text()).toBe("OH2PU-9");
      expect(document.title).toBe("(1) NeoAPRS");
      expect(wrapper.find(".conv.fresh .conv-call").text()).toBe("OH2RDG");
    });

    it("keeps counting a message in the open conversation while the page is hidden, and has seen it when the page is back", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Messages")?.trigger("click");
      await wrapper.find("#pane-messages .conv").trigger("click");
      expect(document.title).toBe("(1) NeoAPRS");
      show("hidden");
      socket.say({ type: "patch", topic: "messages", rev: 1, ops: [{ op: "set", key: "4", value: incoming(4, "OH2PU-9", { text: "Hello again" }) }] });
      await flushPromises();
      expect(document.title).toBe("(2) NeoAPRS");
      show("visible");
      await flushPromises();
      expect(document.title).toBe("(1) NeoAPRS");
    });

    it("keeps counting while the panel is folded or another tab is on show, with the conversation open", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Messages")?.trigger("click");
      await wrapper.find("#pane-messages .conv").trigger("click");
      await tabButton(wrapper, "Packets")?.trigger("click");
      socket.say({ type: "patch", topic: "messages", rev: 1, ops: [{ op: "set", key: "4", value: incoming(4, "OH2PU-9") }] });
      await flushPromises();
      expect(document.title).toBe("(2) NeoAPRS");
      await tabButton(wrapper, "Messages")?.trigger("click");
      expect(document.title).toBe("(1) NeoAPRS");
      await wrapper.find(".panel-fold").trigger("click");
      socket.say({ type: "patch", topic: "messages", rev: 2, ops: [{ op: "set", key: "5", value: incoming(5, "OH2PU-9") }] });
      await flushPromises();
      expect(document.title).toBe("(2) NeoAPRS");
    });

    it("has no Delete button on a message, and the daemon is not asked to delete one", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Messages")?.trigger("click");
      await wrapper.find("#pane-messages .conv").trigger("click");
      expect(wrapper.findAll("#pane-messages .bubble").length).toBeGreaterThan(0);
      expect(wrapper.find("#pane-messages .bubble-delete").exists()).toBe(false);
      expect(JSON.stringify(socket.sent)).not.toContain("message_delete");
    });
  });

  describe("a conversation", () => {
    const conv = (wrapper: VueWrapper, call: string) => wrapper.findAll("#pane-messages .conv").find((c) => c.find(".conv-call").text() === call);
    const x = (wrapper: VueWrapper, call: string) =>
      wrapper
        .findAll("#pane-messages .conv-item")
        .find((c) => c.find(".conv-call").text() === call)
        ?.find(".conv-delete");

    it("is opened by a click on its row, and another row opens that one; the open one is the highlighted row, and a click on it keeps it open", async () => {
      const { wrapper } = await open();
      await tabButton(wrapper, "Messages")?.trigger("click");
      expect(wrapper.find("#pane-messages .conv.active").exists()).toBe(false);
      expect(wrapper.find("#pane-messages .convo-empty").text()).toContain("Choose a conversation");
      await conv(wrapper, "OH2RDG")?.trigger("click");
      expect(wrapper.findAll("#pane-messages .bubble")).toHaveLength(2);
      expect(wrapper.find("#pane-messages .convo-title").text()).toBe("OH2RDG");
      await conv(wrapper, "OH2PU-9")?.trigger("click");
      expect(wrapper.find("#pane-messages .conv.active .conv-call").text()).toBe("OH2PU-9");
      expect(wrapper.find("#pane-messages .convo-title").text()).toBe("OH2PU-9");
      await conv(wrapper, "OH2PU-9")?.trigger("click");
      expect(wrapper.find("#pane-messages .conv.active .conv-call").text()).toBe("OH2PU-9");
      expect(wrapper.findAll("#pane-messages .conv")).toHaveLength(2);
    });

    it("is opened by the Message button of the station's card, again and again, also for a station with no conversation yet, which it creates", async () => {
      const { wrapper, socket } = await open();
      await wrapper
        .findAll("#pane-stations tbody tr")
        .find((r) => r.text().includes("OH2PU-9"))
        ?.trigger("click");
      const message = () => wrapper.findAll(".card .btn").find((b) => b.text() === "Message");
      await message()?.trigger("click");
      expect(wrapper.find("[aria-selected='true']").text()).toContain("Messages");
      expect(wrapper.find("#pane-messages .conv.active .conv-call").text()).toBe("OH2PU-9");
      await message()?.trigger("click");
      expect(wrapper.find("#pane-messages .conv.active .conv-call").text()).toBe("OH2PU-9");
      expect(wrapper.find("#pane-messages .new-message").exists()).toBe(false);
      expect(wrapper.find("#msg-to").exists()).toBe(false);
      await wrapper
        .findAll("#pane-stations tbody tr")
        .find((r) => r.text().includes("OH2NOPOS"))
        ?.trigger("click");
      await message()?.trigger("click");
      expect(wrapper.find("#pane-messages .convo-title").text()).toBe("OH2NOPOS");
      expect(wrapper.find("#pane-messages .bubbles").text()).toContain("No message with OH2NOPOS yet");
      await wrapper.find("#msg-text").setValue("Moi");
      await wrapper.find("#pane-messages form").trigger("submit");
      expect(socket.sent).toContainEqual({ cmd: "send_message", to: "OH2NOPOS", text: "Moi" });
    });

    it("is opened straight, without the list, by the Message button of the station's card on a narrow panel, and Esc is back to the list", async () => {
      setPanelWidth(400);
      const { wrapper } = await open();
      await wrapper
        .findAll("#pane-stations tbody tr")
        .find((r) => r.text().includes("OH2PU-9"))
        ?.trigger("click");
      await wrapper
        .findAll(".card .btn")
        .find((b) => b.text() === "Message")
        ?.trigger("click");
      expect(wrapper.find("#pane-messages .convlist").exists()).toBe(false);
      expect(wrapper.find("#pane-messages .convo-title").text()).toBe("OH2PU-9");
      expect(wrapper.find("#msg-to").exists()).toBe(false);
      await wrapper.find("#pane-messages .convo").trigger("keydown", { key: "Escape" });
      expect(wrapper.find("#pane-messages .convo").exists()).toBe(false);
      expect(wrapper.findAll("#pane-messages .conv")).toHaveLength(2);
    });

    it("is deleted after two clicks on its x, with one command, and its thread closes if it was the open one", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Messages")?.trigger("click");
      await conv(wrapper, "OH2RDG")?.trigger("click");
      await x(wrapper, "OH2RDG")?.trigger("click");
      expect(x(wrapper, "OH2RDG")?.text()).toBe("sure?");
      expect(JSON.stringify(socket.sent)).not.toContain("conversation_delete");
      await x(wrapper, "OH2RDG")?.trigger("click");
      expect(socket.sent).toContainEqual({ cmd: "conversation_delete", call: "OH2RDG" });
      expect(wrapper.find("#pane-messages .conv.active").exists()).toBe(false);
      expect(wrapper.find("#pane-messages .convo").exists()).toBe(false);
      socket.say({
        type: "patch",
        topic: "messages",
        rev: 1,
        ops: [
          { op: "del", key: "1" },
          { op: "del", key: "2" },
        ],
      });
      await flushPromises();
      expect(wrapper.findAll("#pane-messages .conv-call").map((c) => c.text())).toEqual(["OH2PU-9"]);
    });

    it("keeps the open thread when another conversation is deleted", async () => {
      const { wrapper, socket } = await open();
      await tabButton(wrapper, "Messages")?.trigger("click");
      await conv(wrapper, "OH2RDG")?.trigger("click");
      await x(wrapper, "OH2PU-9")?.trigger("click");
      await x(wrapper, "OH2PU-9")?.trigger("click");
      expect(socket.sent).toContainEqual({ cmd: "conversation_delete", call: "OH2PU-9" });
      expect(wrapper.find("#pane-messages .conv.active .conv-call").text()).toBe("OH2RDG");
    });

    it("has an overheard pair deleted after two clicks on its x with one command, when the overheard rows are listed", async () => {
      const { wrapper, socket } = await open();
      const heard = message(20, { direction: "in", state: "overheard", from_call: "OH2AAA", to_call: "OH2BBB", text: "chatter", attempts: 0 });
      socket.say({ type: "patch", topic: "messages", rev: 1, ops: [{ op: "set", key: "20", value: heard }] });
      await flushPromises();
      await tabButton(wrapper, "Messages")?.trigger("click");
      expect(x(wrapper, "OH2AAA > OH2BBB")).toBeUndefined();
      await wrapper.find<HTMLInputElement>("#pane-messages .convlist-overheard input").setValue(true);
      await x(wrapper, "OH2AAA > OH2BBB")?.trigger("click");
      expect(x(wrapper, "OH2AAA > OH2BBB")?.text()).toBe("sure?");
      expect(JSON.stringify(socket.sent)).not.toContain("overheard_delete");
      await x(wrapper, "OH2AAA > OH2BBB")?.trigger("click");
      expect(socket.sent).toContainEqual({ cmd: "overheard_delete", from_call: "OH2AAA", to_call: "OH2BBB" });
      expect(JSON.stringify(socket.sent)).not.toContain("conversation_delete");
    });
  });
});
