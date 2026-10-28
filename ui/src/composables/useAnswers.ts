// The latest answer to each command that is answered with a message of its own, kept for the component that asked: `weather_series`, `packet_history`, `alert_test`, `list_ports`, `find_radio`, `update_check` and `release_notes`; and what the hub (lib/hub.ts) does with them: keep the message.
import { shallowRef } from "vue";
import type { Store } from "@/lib/hub";
import type {
  AlertResultMessage,
  PacketHistoryMessage,
  PortsMessage,
  RadioSearchMessage,
  ReleaseNotesMessage,
  UpdateResultMessage,
  WeatherSeriesMessage,
} from "@/protocol/protocol";

type AnswerHandlers = Pick<Store, "weatherSeries" | "packetHistory" | "alertResult" | "ports" | "radioSearch" | "updateResult" | "releaseNotes">;

export function useAnswers() {
  const weatherSeries = shallowRef<WeatherSeriesMessage | null>(null);
  /** The latest answer for each station: several weather cards are open at once, each with its own graphs. */
  const weatherSeriesByCall = shallowRef<ReadonlyMap<string, WeatherSeriesMessage>>(new Map());
  /** The packets heard by the hour, for the graph of the statistics card (the answer that has no call: every packet heard). */
  const packetHistory = shallowRef<PacketHistoryMessage | null>(null);
  /** The packets of one station by the hour, the latest answer for each: several station cards are open at once, each with its own graph. */
  const packetHistoryByCall = shallowRef<ReadonlyMap<string, PacketHistoryMessage>>(new Map());
  const alertResult = shallowRef<AlertResultMessage | null>(null);
  const ports = shallowRef<PortsMessage | null>(null);
  const updateResult = shallowRef<UpdateResultMessage | null>(null);
  /** What is new up to the version the update dialog asked for. */
  const releaseNotes = shallowRef<ReleaseNotesMessage | null>(null);
  /** The latest `radio_search` of the search the page started: a step, or the end of it. */
  const radioSearch = shallowRef<RadioSearchMessage | null>(null);
  const handlers: AnswerHandlers = {
    weatherSeries: (message) => {
      weatherSeries.value = message;
      weatherSeriesByCall.value = new Map(weatherSeriesByCall.value).set(message.call, message);
    },
    packetHistory: (message) => {
      if (message.call === null) packetHistory.value = message;
      else packetHistoryByCall.value = new Map(packetHistoryByCall.value).set(message.call, message);
    },
    alertResult: (message) => (alertResult.value = message),
    ports: (message) => (ports.value = message),
    updateResult: (message) => (updateResult.value = message),
    releaseNotes: (message) => (releaseNotes.value = message),
    radioSearch: (message) => (radioSearch.value = message),
  };
  /** The answers as the page reads them (useDaemon spreads them into what it returns). */
  const refs = { weatherSeries, weatherSeriesByCall, packetHistory, packetHistoryByCall, alertResult, ports, updateResult, releaseNotes, radioSearch };
  return { ...refs, refs, handlers };
}
