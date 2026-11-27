// The map's traffic layers and their sources as the page names them: the catalogue's id of each
// layer's name (the Layers box and Settings, Map), the sources' own names, which are the same in
// every language, and the credit each service is owed while its layer is on the map. The sources a
// station is offered come from the daemon (`map.layers`, AIRCRAFT_SOURCES and SHIP_SOURCES).
import type { MessageId } from "@/i18n/catalogue";
import { ADSBFI_URL, ADSBLOL_URL, AISSTREAM_URL, CC_BY_URL, DIGITRAFFIC_URL, ODBL_URL } from "@/lib/links";
import type { MapLayer } from "@/protocol/protocol";

/** A layer of traffic. */
export type LayerName = MapLayer["layer"];
/** A source a layer's things may come from. */
export type SourceName = MapLayer["source"];
/** A source on the internet. */
export type ServiceName = Exclude<SourceName, "none" | "receiver" | "radarcape">;
/** A source that is a device of the station's own: no credit is owed and an address is typed. */
export type OwnName = "receiver" | "radarcape";

/** The catalogue's id of each layer's name. */
export const LAYER_NAMES: Readonly<Record<LayerName, MessageId>> = {
  aircraft: "layers.aircraft",
  ships: "layers.ships",
};

/** The Radarcape's name, which no language translates. */
export const RADARCAPE_NAME = "Radarcape";

/** The services by their own names, which no language translates. */
export const SOURCE_NAMES: Readonly<Record<ServiceName, string>> = {
  adsbfi: "adsb.fi",
  adsblol: "adsb.lol",
  fintraffic: "Fintraffic",
  aisstream: "AISStream",
};

/** A piece of a credit: its text, and the address it links to where it is a link. */
export interface CreditPart {
  readonly text: string;
  readonly href?: string;
}

/** The credit of each service, in pieces: the text is the pieces joined, and a piece with an
 * address links to it (opened in a new tab). Own receivers are owed none. */
export const CREDITS: Readonly<Record<ServiceName, readonly CreditPart[]>> = {
  adsbfi: [{ text: "adsb.fi", href: ADSBFI_URL }],
  adsblol: [{ text: "adsb.lol", href: ADSBLOL_URL }, { text: ", " }, { text: "ODbL 1.0", href: ODBL_URL }],
  fintraffic: [
    { text: "Source: " },
    { text: "Fintraffic / digitraffic.fi", href: DIGITRAFFIC_URL },
    { text: ", license " },
    { text: "CC 4.0 BY", href: CC_BY_URL },
  ],
  aisstream: [{ text: "AISStream", href: AISSTREAM_URL }],
};

/** Whether a source is a device of the station's own (a Radarcape, an aircraft receiver or an AIS
 * receiver). */
export const isOwn = (source: string): source is OwnName => source === "receiver" || source === "radarcape";

/** Whether a source is a service on the internet (one with its own name and a credit). */
export const isService = (source: SourceName): source is ServiceName => source in SOURCE_NAMES;
