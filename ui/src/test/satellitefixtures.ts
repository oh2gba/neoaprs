// The satellites layer as the daemon tells it, for the tests: the ISS's card in the middle of a pass
// over Helsinki, as tests/test_satellites_daemon.py has it (rise 12:03:44, set 12:13:06 UTC).
import type { SatelliteCard, SatelliteMark, SatellitesMessage } from "@/protocol/protocol";

export const RISE = "2026-11-28T12:03:44Z";
const SET = "2026-11-28T12:13:06Z";
export const DURING = Date.parse("2026-11-28T12:05:00Z");

export function satelliteMark(id = 25544, name = "ISS", over: Partial<SatelliteMark> = {}): SatelliteMark {
  return {
    id,
    name,
    points: [
      { at: "2026-11-28T12:04:30Z", lat: 44.83, lon: 9.89 },
      { at: "2026-11-28T12:05:00Z", lat: 45.7, lon: 11.5 },
      { at: "2026-11-28T12:05:30Z", lat: 46.5, lon: 13.1 },
    ],
    ...over,
  };
}

export function satelliteCard(over: Partial<SatelliteCard> = {}): SatelliteCard {
  return {
    id: 25544,
    name: "ISS",
    downlinks: [{ hz: 437825000, rise_hz: 437833777, max_hz: 437825004, set_hz: 437816223 }],
    uplinks: [{ hz: 437825000, rise_hz: 437816223, max_hz: 437824996, set_hz: 437833777 }],
    mode: "afsk1200",
    path: "",
    alt_km: 419.9,
    footprint_km: 2252.3,
    track: [
      { at: "2026-11-28T12:05:00Z", lat: 45.7, lon: 11.5 },
      { at: "2026-11-28T12:06:00Z", lat: 47.2, lon: 14.8 },
    ],
    next_pass: {
      rise: RISE,
      set: SET,
      max_at: "2026-11-28T12:08:25Z",
      max_el_deg: 14.7,
      rise_az_deg: 242.3,
      set_az_deg: 115.9,
    },
    looks: [
      { at: "2026-11-28T12:05:00Z", el_deg: 4.0, down_hz: [8400], up_hz: [-8400] },
      { at: "2026-11-28T12:05:05Z", el_deg: 4.5, down_hz: [8300], up_hz: [-8300] },
    ],
    ...over,
  };
}

export function satellitesMessage(over: Partial<SatellitesMessage> = {}): SatellitesMessage {
  return {
    type: "satellites",
    at: "2026-11-28T12:05:00Z",
    elements_at: "2026-11-27T17:59:24Z",
    satellites: [satelliteMark(), satelliteMark(59112, "SONATE-2")],
    cards: [],
    ...over,
  };
}
