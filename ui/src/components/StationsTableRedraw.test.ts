// The Stations table is not drawn again for a patch of the topic `radios` that changes only a
// radio's counts (a radio's row changes with every line its TNC sees, up to four times a
// second). With several radios on, the tags of "Heard on" name the radios; a radio stays the
// same object while nothing of its own changes (composables/useRadios.ts), so the tags read
// nothing of the row that the counts change.
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick, shallowRef } from "vue";
import StationsTable from "@/components/StationsTable.vue";
import * as channels from "@/lib/channels";
import { fakeDaemon, withDaemon } from "@/test/context";
import type { RadioRow } from "@/protocol/protocol";
import { ago, heardBy, lineStats, radioRow, radiosTopic, station, table } from "@/test/fixtures";

vi.mock("@/lib/channels", async (actual) => {
  const real = await actual<typeof channels>();
  return { ...real, heardTags: vi.fn(real.heardTags) };
});

const FM = radioRow(1, "kenwood-tnc2");
const HF = radioRow(2, "mercury");
const N = 20;
const stations = table(
  ...Array.from({ length: N }, (_, i) =>
    station(`OH${i}ABC`, { last_heard: ago(30 + i), heard_rf: 4, heard: heardBy([1, 2, ago(60 + i)], [2, 2, ago(30 + i)]) }),
  ),
);

beforeEach(() => localStorage.clear());

describe("the Stations table with several radios on", () => {
  it("is not drawn again when a patch of a radio changes only its counts, and is when its name changes", async () => {
    const radios = shallowRef<ReadonlyMap<string, RadioRow>>(radiosTopic(FM, HF));
    const wrapper = mount(StationsTable, { props: { selected: null }, global: withDaemon(fakeDaemon({ stations, radios })) });
    await nextTick();
    expect(wrapper.findAll("tbody tr[data-call] .via").at(0)?.text()).toBe("FM");
    const heardTags = vi.mocked(channels.heardTags);
    heardTags.mockClear();
    for (let n = 1; n <= 4; n++) {
      radios.value = new Map(radios.value).set("2", { ...HF, stats: lineStats({ frames_in: 12 + n }) });
      await nextTick();
    }
    expect(heardTags).not.toHaveBeenCalled();
    radios.value = new Map(radios.value).set("2", { ...HF, name: "20 m" });
    await nextTick();
    expect(heardTags).toHaveBeenCalledTimes(N);
    expect(wrapper.text()).toContain("20 m");
  });
});
