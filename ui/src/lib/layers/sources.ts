// The map's layers of traffic and their sources as the page names them: the catalogue's id of each layer's name (the Layers box and Settings, Map), the sources' own names, which are the same in every
// language, and the credit each service is owed while its layer is on the map. The sources a station is offered come from the daemon (`map.layers`, AIRCRAFT_SOURCES and SHIP_SOURCES of the lists).
import type { MessageId } from "@/i18n/catalogue";
import type { MapLayer } from "@/protocol/protocol";

/** A layer of traffic. */
export type LayerName = MapLayer["layer"];
/** A source a layer's things may come from. */
export type SourceName = MapLayer["source"];
/** A source on the internet. */
export type ServiceName = Exclude<SourceName, "none" | "receiver">;

/** The catalogue's id of each layer's name. */
export const LAYER_NAMES: Readonly<Record<LayerName, MessageId>> = { aircraft: "layers.aircraft", ships: "layers.ships" };

/** The services by their own names, which no language translates. */
export const SOURCE_NAMES: Readonly<Record<ServiceName, string>> = { adsbfi: "adsb.fi", adsblol: "adsb.lol", fintraffic: "Fintraffic" };

/** A piece of a credit: its text, and the address it links to where it is a link. */
export interface CreditPart {
  readonly text: string;
  readonly href?: string;
}

/** The credit of each service, in pieces: the text is the pieces one after another, and a piece with an address is a link to it (opened in a new tab). The own receivers are owed none. */
export const CREDITS: Readonly<Record<ServiceName, readonly CreditPart[]>> = {
  adsbfi: [{ text: "adsb.fi", href: "https://adsb.fi/" }],
  adsblol: [{ text: "adsb.lol", href: "https://www.adsb.lol/" }, { text: ", " }, { text: "ODbL 1.0", href: "https://opendatacommons.org/licenses/odbl/1-0/" }],
  fintraffic: [
    { text: "Source: " },
    { text: "Fintraffic / digitraffic.fi", href: "https://www.digitraffic.fi/" },
    { text: ", license " },
    { text: "CC 4.0 BY", href: "https://creativecommons.org/licenses/by/4.0/" },
  ],
};

/** Whether a source is a service on the internet (one with its own name and a credit). */
export const isService = (source: SourceName): source is ServiceName => source in SOURCE_NAMES;
