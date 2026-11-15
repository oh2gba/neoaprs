import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import MessageChain from "@/components/MessageChain.vue";
import type { AttemptRow, HopRow, MessageRow, RadioRow } from "@/protocol/protocol";
import { fakeDaemon, withDaemon } from "@/test/context";
import { attemptRow, incoming, message, radioRow, radiosTopic } from "@/test/fixtures";

const hop = (call: string, extra: Partial<HopRow> = {}): HopRow => ({ call, heard: false, heard_at: null, by_internet: false, ...extra });
const attempt = (at: string, hops: HopRow[], extra: Partial<AttemptRow> = {}): AttemptRow => attemptRow({ sent_at: at, hops, ...extra });
const path = (...calls: string[]) => calls.map((call) => hop(call));
const show = (row: MessageRow, heardDirect: string[] = []) => mount(MessageChain, { props: { row, heardDirect: new Set(heardDirect) } });
const texts = (wrapper: ReturnType<typeof show>, selector = ".chain-latest .chip-hop") => wrapper.findAll(selector).map((c) => c.text().replace(/\s+/g, " "));

describe("MessageChain", () => {
  it("shows the chips of the latest attempt: you, the digipeaters with their marks, the recipient", () => {
    const row = message(1, {
      to_call: "OH2CUB-7",
      attempts_detail: [attempt("2026-10-22T12:00:00Z", [hop("OH2RCH-2", { heard: true, heard_at: "2026-10-22T12:00:05Z" }), hop("OH2RDG")])],
    });
    const wrapper = show(row);
    expect(texts(wrapper)).toEqual(["you", "→OH2RCH-2✓", "→OH2RDG?", "→OH2CUB-7"]);
    expect(wrapper.findAll(".chip-hop").map((c) => c.attributes("data-kind"))).toEqual(["you", "heard", "unheard", "waiting"]);
  });

  it("gives a hop that was heard a check, the heard class and the time, and one that was not the title that says why", () => {
    const row = message(1, {
      attempts_detail: [attempt("2026-10-22T12:00:00Z", [hop("OH2RCH-2", { heard: true, heard_at: "2026-10-22T12:00:05Z" }), hop("OH2RDG"), hop("OH2XYZ")])],
    });
    const items = show(row, ["OH2XYZ"]).findAll(".chip-hop");
    expect(items[1]?.classes()).toContain("hop-heard");
    expect(items[1]?.attributes("title")).toMatch(/^heard /);
    expect(items[2]?.classes()).toContain("hop-unheard");
    expect(items[2]?.attributes("title")).toBe("not heard here: beyond what this station can hear");
    expect(items[3]?.attributes("title")).toBe("not heard");
  });

  it("shows a hop seen only over the internet as internet, and the recipient plain on the ack and orange on failure", () => {
    const seen = [hop("OH2RDG", { by_internet: true, heard_at: "2026-10-22T12:00:05Z" })];
    const internet = show(message(1, { attempts_detail: [attempt("2026-10-22T12:00:00Z", seen)] })).findAll(".chip-hop");
    expect([internet[1]?.classes(), internet[1]?.text()]).toEqual([expect.arrayContaining(["hop-internet"]), "→OH2RDGinternet"]);
    const acked = show(
      message(1, { state: "acked", acked_at: "2026-10-22T12:00:09Z", attempts_detail: [attempt("2026-10-22T12:00:00Z", [], { acked: true })] }),
    ).findAll(".chip-hop");
    expect(acked.at(-1)?.classes()).toContain("hop-acked");
    const failed = show(message(1, { state: "failed", attempts_detail: [attempt("2026-10-22T12:00:00Z", [])] })).findAll(".chip-hop");
    expect(failed.at(-1)?.classes()).toContain("hop-failed");
    expect(failed.at(-1)?.text()).toContain("✗");
  });

  it("shows only the chain of the latest attempt of a message sent several times, with no line of attempts", () => {
    const row = message(1, {
      to_call: "OH2CUB-7",
      state: "acked",
      acked_at: "2026-10-22T12:01:10Z",
      attempts: 3,
      attempts_detail: [
        attempt("2026-10-22T12:00:00Z", [hop("OH2RCH-2", { heard: true, heard_at: "2026-10-22T12:00:03Z" }), hop("OH2RDG")]),
        attempt("2026-10-22T12:00:30Z", path("OH2RCH-2", "OH2RDG")),
        attempt(
          "2026-10-22T12:01:00Z",
          [hop("OH2RCH-2", { heard: true, heard_at: "2026-10-22T12:01:02Z" }), hop("OH2RDG", { heard: true, heard_at: "2026-10-22T12:01:05Z" })],
          { acked: true },
        ),
      ],
    });
    const wrapper = show(row);
    expect(texts(wrapper)).toEqual(["you", "→OH2RCH-2✓", "→OH2RDG✓", "→OH2CUB-7✓"]);
    expect(wrapper.find("details").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("attempts");
  });

  it("adds an internet chip when a copy came back that way and no hop shows it", () => {
    const row = message(1, { to_call: "OH2CUB-7", attempts_detail: [attempt("2026-10-22T12:00:00Z", path("OH2RCH-2"), { internet: "OH7JHF-1" })] });
    const wrapper = show(row);
    expect(texts(wrapper)).toEqual(["you", "→OH2RCH-2?", "→internet", "→OH2CUB-7"]);
    expect(wrapper.findAll(".chip-hop")[2]?.attributes("title")).toContain("OH7JHF-1");
  });

  it("draws nothing for a message that has no attempt kept, or one that came in", () => {
    expect(show(message(1)).find(".chain").exists()).toBe(false);
    expect(show(incoming(2, "OH2RDG")).find(".chain").exists()).toBe(false);
  });

  it("names the radio of the attempt on the you chip where radios are named, FM as HF, and none with one radio on", () => {
    const off = { enabled: false, state: "stopped" } as const;
    const both = radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury"));
    const fmAlone = radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury", off));
    const hfAlone = radiosTopic(radioRow(1, "kenwood-tnc2", off), radioRow(2, "mercury"));
    const sent = (radio: number, radios: ReadonlyMap<string, RadioRow>) =>
      mount(MessageChain, {
        props: { row: message(1, { to_call: "OH2CUB-7", attempts_detail: [attempt("2026-10-22T12:00:00Z", [], { radio_id: radio })] }) },
        global: withDaemon(fakeDaemon({ radios })),
      })
        .find(".chips li")
        .text();
    expect([sent(1, both), sent(2, both)]).toEqual(["youFM", "youHF"]);
    expect([sent(1, fmAlone), sent(2, hfAlone)]).toEqual(["you", "you"]);
    expect(sent(2, fmAlone)).toBe("youHF"); // (a radio that is not on is always named)
  });

  it("names a third radio, and one removed since, by its name", () => {
    const radios = radiosTopic(
      radioRow(1, "kenwood-tnc2"),
      radioRow(3, "kiss", { name: "Mobile", number: 2 }),
      radioRow(4, "kiss", { name: "Old", number: 3, removed: true, enabled: false, state: "stopped" }),
    );
    const on = (id: number) =>
      mount(MessageChain, {
        props: { row: message(1, { attempts_detail: [attempt("2026-10-22T12:00:00Z", [], { radio_id: id })] }) },
        global: withDaemon(fakeDaemon({ radios })),
      }).find(".chips li");
    expect([on(3).text(), on(4).text(), on(1).text()]).toEqual(["youMobile", "youOld", "youFM"]);
  });

  it("uses only the page's colour variables, so that both schemes show it", () => {
    const html = show(message(1, { attempts_detail: [attempt("2026-10-22T12:00:00Z", path("OH2RCH-2"))] })).html();
    expect(html).not.toMatch(/#[0-9a-f]{3,6}|rgb\(/i);
  });
});
