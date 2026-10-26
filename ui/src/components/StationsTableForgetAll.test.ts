import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StationsTable from "@/components/StationsTable.vue";
import { fakeDaemon, withDaemon } from "@/test/context";
import { ago, station, table } from "@/test/fixtures";

const heard = table(
  station("OH2GBA", { is_me: true, distance_km: null, bearing_deg: null, last_heard: ago(10) }),
  station("OH2RDG", { distance_km: 25, last_heard: ago(20) }),
  station("OH2OBJ", { kind: "object", can_message: false, reported_by: "OH2GBA", own: true, last_heard: ago(50) }),
);
const alone = table(station("OH2GBA", { is_me: true, distance_km: null, bearing_deg: null, last_heard: ago(10) }));
function make(stations = heard) {
  const daemon = fakeDaemon({ stations, aging: { defaultMin: 0 } });
  const wrapper = mount(StationsTable, { props: { selected: null }, global: withDaemon(daemon) });
  return { wrapper, daemon, button: () => wrapper.find(".foot button.forgetall") };
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.useRealTimers());

describe("Forget all at the foot of the Stations table", () => {
  it("asks twice: the first press says Really forget all? and sends nothing, the second sends the command", async () => {
    const { button, daemon } = make();
    expect(button().text()).toBe("Forget all");
    await button().trigger("click");
    expect(daemon.send).not.toHaveBeenCalled();
    expect(button().text()).toBe("Really forget all?");
    expect(button().classes()).toContain("danger");
    await button().trigger("click");
    expect(daemon.send).toHaveBeenCalledExactlyOnceWith({ cmd: "forget_all_stations" });
    expect(button().text()).toBe("Forget all");
    expect(button().classes()).not.toContain("danger");
  });

  it("takes the question back after 5 seconds", async () => {
    vi.useFakeTimers();
    const { button, daemon } = make();
    await button().trigger("click");
    vi.advanceTimersByTime(5001);
    await button().trigger("click");
    expect(daemon.send).not.toHaveBeenCalled();
    expect(button().text()).toBe("Really forget all?");
  });

  it("has an (i) that says what goes and what stays, and is greyed while only our own station and objects are in the list", () => {
    const { wrapper, button } = make();
    expect(button().attributes("disabled")).toBeUndefined();
    expect(wrapper.find(".foot .infotip button").attributes("aria-label")).toBe("About Forget all");
    const bare = make(alone);
    expect(bare.button().attributes("disabled")).toBeDefined();
    expect(bare.wrapper.find(".foot .infotip").exists()).toBe(true);
  });

  it("is a small button with the count beside it, and no inline style", () => {
    const { wrapper, button } = make();
    expect(button().classes()).toEqual(expect.arrayContaining(["btn", "small"]));
    expect(button().attributes("style")).toBeUndefined();
    expect(wrapper.find(".foot").text()).toContain("of 3 stations");
  });
});
