import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import AppHeader from "@/components/AppHeader.vue";
import { cssRule, mediaRule } from "@/test/css";

const header = (props: Partial<InstanceType<typeof AppHeader>["$props"]> = {}) => mount(AppHeader, { props: { call: "OH2GBA", unread: 0, ...props } });

describe("AppHeader", () => {
  it("has the title as a link to the project page that opens in a new tab and cannot reach back to the page", () => {
    const link = header().find("h1 a");
    expect(link.text()).toBe("NeoAPRS");
    expect(link.attributes("href")).toBe("https://oh2gba.github.io/neoaprs/");
    expect(link.attributes("target")).toBe("_blank");
    expect(link.attributes("rel")).toBe("noopener");
  });

  it("makes the link look like the title: its colour and weight, no underline, an underline on hover and a ring for the keyboard", () => {
    expect(header().find("h1 a").classes()).toContain("brand");
    const rule = cssRule(".brand");
    expect(rule).toMatch(/color:\s*inherit/);
    expect(rule).toMatch(/font-weight:\s*inherit/);
    expect(rule).toMatch(/text-decoration:\s*none/);
    expect(cssRule(".brand:hover")).toMatch(/text-decoration:\s*underline/);
    expect(cssRule(".brand:focus-visible")).toMatch(/outline:\s*2px solid var\(--accent\)/);
  });

  it("does not show our call, the radio, the version or an update: those are in the footer of the panel", () => {
    const wrapper = header({ unread: 3 });
    expect(wrapper.find(".call").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("OH2GBA");
    expect(wrapper.text()).not.toMatch(/radio|daemon|update|v\d/i);
    expect(wrapper.find(".status").exists()).toBe(false);
    expect(wrapper.find(".version").exists()).toBe(false);
    expect(wrapper.find(".update").exists()).toBe(false);
  });

  it("shows the number of messages not seen as a button of its own, and a click asks for them", async () => {
    const wrapper = header({ unread: 2 });
    const mail = wrapper.find("button.headmail");
    expect(mail.text()).toContain("2");
    expect(mail.attributes("title")).toBe("2 messages not seen yet: open the messages");
    expect(mail.find(".sr-only").text()).toBe("2 messages not seen yet");
    expect(mail.element.parentElement).toBe(wrapper.element);
    await mail.trigger("click");
    expect(wrapper.emitted("messages")).toHaveLength(1);
  });

  it("shows nothing when all are seen", () => {
    expect(header().find(".headmail").exists()).toBe(false);
  });

  it("puts the badge at the right of the line, away from the title", () => {
    expect(cssRule(".headmail.badge")).toMatch(/margin:\s*0 0 0 auto/);
  });

  it('shows an amber button "no call set" while the call is empty, and a click asks for the setup guide', async () => {
    const wrapper = header({ call: "" });
    const button = wrapper.find(".nocall");
    expect(button.text()).toBe("no call set");
    await button.trigger("click");
    expect(wrapper.emitted("setup")).toHaveLength(1);
    expect(header().find(".nocall").exists()).toBe(false);
    expect(header({ call: null }).find(".nocall").exists()).toBe(false);
  });

  it("shows the amber Receive only badge beside the title while transmitting is off, a plain badge and not a button", async () => {
    const wrapper = header({ receiveOnly: true });
    const badge = wrapper.find(".rxonly");
    expect(badge.text()).toBe("Receive only");
    expect(badge.element.tagName).toBe("SPAN");
    expect(badge.element.previousElementSibling?.tagName).toBe("H1");
    expect(cssRule(".rxonly")).toMatch(/color:\s*var\(--warn\)/);
    expect(cssRule(".rxonly")).not.toMatch(/cursor:\s*pointer/);
    expect(wrapper.findAll("button").some((b) => b.text() === "Receive only")).toBe(false);
    expect(badge.attributes("tabindex")).toBeUndefined();
    await badge.trigger("click");
    expect(wrapper.emitted()).not.toHaveProperty("receive");
    expect(wrapper.emitted("setup")).toBeUndefined();
    expect(header().find(".rxonly").exists()).toBe(false);
    expect(header({ receiveOnly: false }).find(".rxonly").exists()).toBe(false);
  });

  it("says in the hover title of the badge what it means and where it is set: the daemon's setting station/transmit, not on the page", () => {
    const title = header({ receiveOnly: true }).find(".rxonly").attributes("title");
    expect(title).toContain("Nothing is transmitted: this station is set to receive only");
    expect(title).toContain("station/transmit");
    expect(title).toContain("not on this page");
    expect(title).toContain("neoaprs db set station/transmit true");
    expect(title).toContain("next start");
  });

  it("has no hit area of a finger around the badge, which does nothing", () => {
    expect(mediaRule("(pointer: coarse)", ".rxonly::after")).toBe("");
    expect(mediaRule("(pointer: coarse)", ".nocall::after")).toContain("inset");
  });

  it("is as high with a badge and a button as without them", () => {
    expect(cssRule(".appheader")).toMatch(/min-height:\s*34px/);
  });
});
