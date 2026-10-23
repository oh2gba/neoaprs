import { describe, expect, it, vi } from "vitest";
import { nextTick, ref, shallowReactive } from "vue";
import { usePageAlerts } from "@/composables/usePageAlerts";
import { incoming, message } from "@/test/fixtures";
import type { MessageRow } from "@/protocol/protocol";

function make(initial: MessageRow[] = []) {
  const messages = shallowReactive(new Map<string, MessageRow>());
  const loaded = ref(false);
  const announce = vi.fn();
  usePageAlerts(messages, loaded, announce);
  const fill = (rows: MessageRow[]) => {
    messages.clear();
    for (const row of rows) messages.set(String(row.id), row);
    loaded.value = true;
  };
  if (initial.length > 0) fill(initial);
  return { messages, loaded, announce, fill };
}

const ids = (announce: ReturnType<typeof vi.fn>): number[][] => announce.mock.calls.map((call) => (call[0] as MessageRow[]).map((m) => m.id));

describe("usePageAlerts", () => {
  it("alerts nothing for the messages the page loaded with", async () => {
    const { announce, fill } = make();
    fill([incoming(1, "OH2RDG"), incoming(2, "OH2PU-9")]);
    await nextTick();
    expect(announce).not.toHaveBeenCalled();
  });

  it("alerts once for a message that arrives after, and not again when the row changes", async () => {
    const { announce, fill, messages } = make();
    fill([incoming(1, "OH2RDG")]);
    await nextTick();
    messages.set("2", incoming(2, "OH2PU-9"));
    await nextTick();
    messages.set("2", incoming(2, "OH2PU-9", { route: "direct" }));
    await nextTick();
    expect(ids(announce)).toEqual([[2]]);
  });

  it("alerts for none of the ones we overheard, the ones of ours, or the ones sent before", async () => {
    const { announce, fill, messages } = make();
    fill([incoming(5, "OH2RDG")]);
    await nextTick();
    messages.set("6", incoming(6, "OH2XYZ", { state: "overheard", to_call: "OH2ABC" }));
    messages.set("7", message(7, { to_call: "OH2RDG" }));
    messages.set("3", incoming(3, "OH2PU-9"));
    await nextTick();
    expect(announce).not.toHaveBeenCalled();
  });

  it("alerts nothing when the daemon tells the same messages again after a reconnect, and the ones that came meanwhile once", async () => {
    const { announce, fill } = make();
    const old = [incoming(1, "OH2RDG"), incoming(2, "OH2PU-9")];
    fill(old);
    await nextTick();
    fill(old); // the socket opened again: the topic is told whole
    await nextTick();
    expect(announce).not.toHaveBeenCalled();
    fill([...old, incoming(3, "OH2DPN")]);
    await nextTick();
    fill([...old, incoming(3, "OH2DPN")]);
    await nextTick();
    expect(ids(announce)).toEqual([[3]]);
  });

  it("waits for the first state of the topic: an empty map is not a baseline", async () => {
    const { announce, fill, messages } = make();
    messages.set("1", incoming(1, "OH2RDG"));
    await nextTick();
    expect(announce).not.toHaveBeenCalled();
    fill([incoming(1, "OH2RDG")]);
    await nextTick();
    expect(announce).not.toHaveBeenCalled();
  });
});
