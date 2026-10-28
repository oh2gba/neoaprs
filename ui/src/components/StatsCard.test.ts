import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { shallowRef } from "vue";
import StatsCard from "@/components/StatsCard.vue";
import { fakeDaemon, withDaemon } from "@/test/context";
import { NOW, packet, station, status, table, tncState } from "@/test/fixtures";

afterEach(() => document.body.replaceChildren());

const stations = () =>
  table(
    station("OH2GBA", { is_me: true, lat: 60.17, lon: 24.94 }),
    station("OH2PU-9", { lat: 60.2, lon: 24.65, distance_km: 16, heard_direct: 3, heard_rf: 20, packets_hour: 12 }),
    station("OH2RDG", { lat: 60.12, lon: 24.49, distance_km: 25, heard_rf: 5, packets_hour: 2 }),
  );

describe("StatsCard", () => {
  it("shows the sections with their lines, and its cross closes it", async () => {
    const daemon = fakeDaemon({ stations: stations(), status: status({ packets: 321 }), tnc: tncState() });
    const wrapper = mount(StatsCard, {
      props: { packets: new Map([["1", packet(1, { route: "direct" })]]) },
      global: withDaemon(daemon),
      attachTo: document.body,
    });
    expect(wrapper.find(".card-head strong").text()).toBe("Statistics");
    expect(wrapper.findAll("h3.stats-section").map((h) => h.text())).toEqual(["Stations", "Reach", "Packets", "Since the daemon started"]);
    const rows = Object.fromEntries(wrapper.findAll("dt").map((dt, i) => [dt.text(), wrapper.findAll("dd")[i]?.text()]));
    expect(rows["Heard"]).toBe("2");
    expect(rows["Farthest direct"]).toBe("OH2PU-9, 16 km");
    expect(rows["In the database"]).toBe("321");
    expect(rows["Latest 1 by kind"]).toBe("1 positions");
    await wrapper.find(".card-close").trigger("click");
    expect(wrapper.emitted("close")).toHaveLength(1);
  });

  it("moves as the stations do", async () => {
    const rows = shallowRef(stations());
    const daemon = fakeDaemon({ stations: rows });
    const wrapper = mount(StatsCard, { props: { packets: new Map() }, global: withDaemon(daemon) });
    const heard = () => wrapper.findAll("dt").find((dt) => dt.text() === "Heard")?.element.nextElementSibling?.textContent;
    expect(heard()).toBe("2");
    rows.value = table(...rows.value.values(), station("OH2NEW", { lat: 60.3, lon: 25.0 }));
    await wrapper.vm.$nextTick();
    expect(heard()).toBe("3");
  });

  it("asks the daemon for the packets by the hour when it opens and every minute, and draws them as bars once they came", async () => {
    const now = shallowRef(NOW);
    const daemon = fakeDaemon({ stations: stations(), now });
    const wrapper = mount(StatsCard, { props: { packets: new Map() }, global: withDaemon(daemon) });
    expect(daemon.send).toHaveBeenCalledWith({ cmd: "packet_history", hours: 24 });
    expect(wrapper.find(".stats-chart").exists()).toBe(false);
    daemon.packetHistory.value = { type: "packet_history", hours: 24, start: "2026-10-20T13:00:00Z", counts: Array.from({ length: 24 }, (_, i) => i + 1) };
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".stats-chart .trend-head").text()).toContain("Packets an hour, the last 24 hours");
    expect(wrapper.findAll(".stats-chart .trend-bar")).toHaveLength(24);
    expect(wrapper.find(".stats-chart .trend-read").text()).toBe("24 packets");
    now.value = NOW + 30_000;
    await wrapper.vm.$nextTick();
    expect(daemon.send).toHaveBeenCalledTimes(1);
    now.value = NOW + 61_000;
    await wrapper.vm.$nextTick();
    expect(daemon.send).toHaveBeenCalledTimes(2);
  });
});
