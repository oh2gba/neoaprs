// The latest answer to each command that is answered with a message of its own, kept for the component that asked: `weather_series`, `alert_test`, `list_ports`, `find_radio` and `update_check`; and what the hub (lib/hub.ts) does with them: keep the message.
import { shallowRef } from "vue";
import type { Store } from "@/lib/hub";
import type { AlertResultMessage, PortsMessage, RadioSearchMessage, UpdateResultMessage, WeatherSeriesMessage } from "@/protocol/protocol";

type AnswerHandlers = Pick<Store, "weatherSeries" | "alertResult" | "ports" | "radioSearch" | "updateResult">;

export function useAnswers() {
  const weatherSeries = shallowRef<WeatherSeriesMessage | null>(null);
  /** The latest answer for each station: several weather cards are open at once, each with its own graphs. */
  const weatherSeriesByCall = shallowRef<ReadonlyMap<string, WeatherSeriesMessage>>(new Map());
  const alertResult = shallowRef<AlertResultMessage | null>(null);
  const ports = shallowRef<PortsMessage | null>(null);
  const updateResult = shallowRef<UpdateResultMessage | null>(null);
  /** The latest `radio_search` of the search the page started: a step, or the end of it. */
  const radioSearch = shallowRef<RadioSearchMessage | null>(null);
  const handlers: AnswerHandlers = {
    weatherSeries: (message) => {
      weatherSeries.value = message;
      weatherSeriesByCall.value = new Map(weatherSeriesByCall.value).set(message.call, message);
    },
    alertResult: (message) => (alertResult.value = message),
    ports: (message) => (ports.value = message),
    updateResult: (message) => (updateResult.value = message),
    radioSearch: (message) => (radioSearch.value = message),
  };
  return { weatherSeries, weatherSeriesByCall, alertResult, ports, updateResult, radioSearch, handlers };
}
