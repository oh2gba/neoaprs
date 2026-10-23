// The latest answer to each command that is answered with a message of its own, kept for the component that asked: `weather_series`, `alert_test`, `list_ports` and `update_check`; and what the hub (lib/hub.ts) does with them: keep the message.
import { shallowRef } from "vue";
import type { Store } from "@/lib/hub";
import type { AlertResultMessage, PortsMessage, UpdateResultMessage, WeatherSeriesMessage } from "@/protocol/protocol";

type AnswerHandlers = Pick<Store, "weatherSeries" | "alertResult" | "ports" | "updateResult">;

export function useAnswers() {
  const weatherSeries = shallowRef<WeatherSeriesMessage | null>(null);
  const alertResult = shallowRef<AlertResultMessage | null>(null);
  const ports = shallowRef<PortsMessage | null>(null);
  const updateResult = shallowRef<UpdateResultMessage | null>(null);
  const handlers: AnswerHandlers = {
    weatherSeries: (message) => (weatherSeries.value = message),
    alertResult: (message) => (alertResult.value = message),
    ports: (message) => (ports.value = message),
    updateResult: (message) => (updateResult.value = message),
  };
  return { weatherSeries, alertResult, ports, updateResult, handlers };
}
