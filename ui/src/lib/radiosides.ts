// Which of the two radios (FM, HF) something concerns: whether each is switched on (the settings `fm/enabled` and `hf/enabled`: FM is on unless the values say off, HF off unless they say on), and which radio a station is messaged on. The daemon chooses the same way
// (neoaprs/radios.py): a station heard on FM, or on neither, is messaged on FM; one heard on HF alone, on HF. The paths, the route of a station and the requests that carry a path are FM's, since an HF frame goes direct.
import type { StationRow } from "@/protocol/protocol";

type Values = Readonly<Record<string, string>>;
type HeardOn = Pick<StationRow, "heard_fm" | "heard_hf">;

/** The radios, by the word the wire and the settings use. */
export type RadioKind = "fm" | "hf";

/** Whether the FM radio is on in these settings (before the daemon has told them: on, as the default is). */
export const fmOn = (values: Values): boolean => values["fm/enabled"] !== "false";

/** Whether the HF radio is on in these settings. */
export const hfOn = (values: Values): boolean => values["hf/enabled"] === "true";

/** The radio a station is messaged on: HF when it was heard on HF alone, else FM (also for a station nothing was heard of, or none known: null). */
export function stationRadio(row: HeardOn | null | undefined): RadioKind {
  return row != null && row.heard_hf > 0 && row.heard_fm === 0 ? "hf" : "fm";
}

/** The radio a message to a station goes over, as the daemon chooses it (neoaprs/radios.py `for_station`) from the settings and what was heard: the one radio that is on; with both, FM unless the station was heard on HF alone. */
export function radioFor(row: HeardOn | null | undefined, values: Values): RadioKind {
  if (!hfOn(values)) return "fm";
  if (!fmOn(values)) return "hf";
  return stationRadio(row);
}

/** Whether the path controls (Route, the path of a request, RF only) are there: the FM radio is on and, for a station (`row` given, null when none is known), it is the radio it is messaged on. */
export const hasPaths = (values: Values, row?: HeardOn | null): boolean => fmOn(values) && (row === undefined || radioFor(row, values) === "fm");
