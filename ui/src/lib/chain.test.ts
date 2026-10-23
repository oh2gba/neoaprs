import { describe, expect, it } from "vitest";
import { chainOf, isAlias, isMarker } from "@/lib/chain";
import type { AttemptRow, HopRow } from "@/protocol/protocol";
import { message } from "@/test/fixtures";

const hop = (call: string, extra: Partial<HopRow> = {}): HopRow => ({ call, heard: false, heard_at: null, by_internet: false, ...extra });
const attempt = (hops: HopRow[], extra: Partial<AttemptRow> = {}): AttemptRow => ({
  sent_at: "2026-10-22T12:00:00Z",
  hops,
  internet: null,
  acked: false,
  ...extra,
});
const row = message(1, { to_call: "OH2CUB-7" });

describe("chainOf", () => {
  it("is us, each digipeater of the path, and the recipient", () => {
    const chips = chainOf(row, attempt([hop("OH2RCH-2"), hop("OH2RDG")]), true);
    expect(chips.map((c) => c.text)).toEqual(["you", "OH2RCH-2", "OH2RDG", "OH2CUB-7"]);
    expect(chips.map((c) => c.kind)).toEqual(["you", "unheard", "unheard", "waiting"]);
  });

  it("has no chip for RFONLY, NOGATE, TCPIP, TCPXX or a q-construct, which are no hops", () => {
    const hops = [hop("OH2RCH-2"), hop("NOGATE"), hop("OH2RDG"), hop("TCPIP"), hop("TCPXX"), hop("qAR"), hop("RFONLY")];
    expect(chainOf(row, attempt(hops), true).map((c) => c.text)).toEqual(["you", "OH2RCH-2", "OH2RDG", "OH2CUB-7"]);
    expect(chainOf(row, attempt([hop("RFONLY")]), true).map((c) => c.text)).toEqual(["you", "OH2CUB-7"]);
  });

  it("is only us and the recipient for a direct path", () => {
    expect(chainOf(row, attempt([]), true).map((c) => c.text)).toEqual(["you", "OH2CUB-7"]);
  });

  it("shows a hop that was heard green with a check and the time for the title", () => {
    const [, chip] = chainOf(row, attempt([hop("OH2RCH-2", { heard: true, heard_at: "2026-10-22T12:00:05Z" })]), true);
    expect([chip?.kind, chip?.mark, chip?.title.startsWith("heard ")]).toEqual(["heard", "✓", true]);
  });

  it("says a hop was also seen over the internet when both were", () => {
    const [, chip] = chainOf(row, attempt([hop("OH2RCH-2", { heard: true, heard_at: "2026-10-22T12:00:05Z", by_internet: true })]), true);
    expect(chip?.title).toContain("and over the internet");
  });

  it("shows a hop seen only in a copy an iGate gated back as internet, and says it was not heard here", () => {
    const [, chip] = chainOf(row, attempt([hop("OH2RDG", { by_internet: true, heard_at: "2026-10-22T12:00:05Z" })]), true);
    expect([chip?.kind, chip?.mark]).toEqual(["internet", "internet"]);
    expect(chip?.title).toContain("not heard here");
  });

  it("shows a hop that was not heard grey with a ?, and says it is beyond what this station can hear when that digipeater was never heard direct", () => {
    const [, never, direct] = chainOf(row, attempt([hop("OH2RDG"), hop("OH2RCH-2")]), true, new Set(["OH2RCH-2"]));
    expect([never?.kind, never?.mark, never?.title]).toEqual(["unheard", "?", "not heard here: beyond what this station can hear"]);
    expect([direct?.kind, direct?.mark, direct?.title]).toEqual(["unheard", "?", "not heard"]);
  });

  it("calls an alias that was not heard just 'not heard', as no one station is meant", () => {
    const [, chip] = chainOf(row, attempt([hop("WIDE1-1")]), true);
    expect(chip?.title).toBe("not heard");
  });

  it("adds a blue internet chip before the recipient when a copy came back over the internet and no hop shows it", () => {
    const chips = chainOf(row, attempt([hop("OH2RCH-2")], { internet: "OH7JHF-1" }), true);
    expect(chips.map((c) => c.text)).toEqual(["you", "OH2RCH-2", "internet", "OH2CUB-7"]);
    expect(chips[2]?.kind).toBe("internet");
    expect(chips[2]?.title).toContain("OH7JHF-1");
    const shown = chainOf(row, attempt([hop("OH2RCH-2", { by_internet: true })], { internet: "OH7JHF-1" }), true);
    expect(shown.map((c) => c.text)).toEqual(["you", "OH2RCH-2", "OH2CUB-7"]);
  });

  it("makes the recipient green on the ack, with the time of the ack for the title", () => {
    const acked = message(1, { to_call: "OH2CUB-7", state: "acked", acked_at: "2026-10-22T12:00:09Z" });
    const last = chainOf(acked, attempt([], { acked: true }), true).at(-1);
    expect([last?.kind, last?.mark, last?.title.startsWith("acked ")]).toEqual(["acked", "✓", true]);
  });

  it("makes the recipient red on failure and on a rejection, on the latest attempt only", () => {
    const failed = message(1, { to_call: "OH2CUB-7", state: "failed", attempts: 6 });
    expect(chainOf(failed, attempt([]), true).at(-1)).toMatchObject({ kind: "failed", mark: "✗", title: "no answer after 6 attempts" });
    expect(chainOf(failed, attempt([]), false).at(-1)?.kind).toBe("waiting");
    const rejected = message(1, { to_call: "OH2CUB-7", state: "rejected" });
    expect(chainOf(rejected, attempt([]), true).at(-1)).toMatchObject({ kind: "failed", title: "rejected" });
  });

  it("leaves the recipient grey while it waits, and says why when it is not waiting", () => {
    const waiting = (state: "sending" | "unconfirmed" | "cancelled", latest = true) => chainOf(message(1, { state }), attempt([]), latest).at(-1);
    expect(waiting("sending")).toMatchObject({ kind: "waiting", mark: "", title: "waiting for the ack" });
    expect(waiting("unconfirmed")?.title).toBe("sent, no ack expected");
    expect(waiting("cancelled")?.title).toBe("cancelled");
    expect(waiting("sending", false)?.title).toBe("no ack after this attempt");
  });
});

describe("isMarker", () => {
  it("knows the markers for the iGates from digipeaters", () => {
    for (const marker of ["RFONLY", "NOGATE", "TCPIP", "TCPXX", "NOTCP", "qAR", "qAC"]) expect(isMarker(marker)).toBe(true);
    for (const call of ["OH2RCH-2", "WIDE1-1", "RELAY", "OH2RDG"]) expect(isMarker(call)).toBe(false);
  });
});

describe("isAlias", () => {
  it("knows the aliases of a path from calls", () => {
    expect(["WIDE1-1", "WIDE2-2", "TRACE3-3", "RELAY", "WIDE2"].map(isAlias)).toEqual([true, true, true, true, true]);
    expect(["OH2RCH-2", "OH2RDG", "WIDEX-1"].map(isAlias)).toEqual([false, false, false]);
  });
});

describe("chainOf for mail", () => {
  it("leaves the gateway grey, not red, when its ack never came: it reaches us only through an iGate", () => {
    const mail = message(2, { to_call: "EMAIL-2", state: "failed", attempts: 4 });
    const last = chainOf(mail, attempt([]), true, new Set(), true).at(-1);
    expect(last?.kind).toBe("waiting");
    expect(last?.title).toContain("not confirmed");
    expect(chainOf(mail, attempt([]), true).at(-1)?.kind).toBe("failed");
  });
});
