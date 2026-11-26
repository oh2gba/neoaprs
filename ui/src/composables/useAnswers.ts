// The latest answer to each command that has a message of its own, kept for the asking component.
import { shallowRef } from "vue";
import type { Store } from "@/lib/hub";
import type {
  AlertResultMessage,
  SavedMessage,
  PacketHistoryMessage,
  PacketStatsMessage,
  PortsMessage,
  PositionHistoryMessage,
  RadioSearchMessage,
  ReleaseNotesMessage,
  SignalSeriesMessage,
  SpeedSeriesMessage,
  StationTrafficMessage,
  UpdateResultMessage,
  WeatherSeriesMessage,
} from "@/protocol/protocol";

type AnswerHandlers = Pick<
  Store,
  | "weatherSeries"
  | "packetHistory"
  | "packetStats"
  | "speedSeries"
  | "signalSeries"
  | "stationTraffic"
  | "positionHistory"
  | "alertResult"
  | "saved"
  | "ports"
  | "radioSearch"
  | "updateResult"
  | "releaseNotes"
>;

export function useAnswers() {
  const weatherSeries = shallowRef<WeatherSeriesMessage | null>(null);
  const weatherSeriesByCall = shallowRef<ReadonlyMap<string, WeatherSeriesMessage>>(new Map());
  const packetHistory = shallowRef<PacketHistoryMessage | null>(null);
  const packetStats = shallowRef<PacketStatsMessage | null>(null);
  const packetHistoryByCall = shallowRef<ReadonlyMap<string, PacketHistoryMessage>>(new Map());
  const speedSeriesByCall = shallowRef<ReadonlyMap<string, SpeedSeriesMessage>>(new Map());
  const signalSeriesByCall = shallowRef<ReadonlyMap<string, SignalSeriesMessage>>(new Map());
  const stationTrafficByCall = shallowRef<ReadonlyMap<string, StationTrafficMessage>>(new Map());
  const positionHistory = shallowRef<PositionHistoryMessage | null>(null);
  const alertResult = shallowRef<AlertResultMessage | null>(null);
  const saved = shallowRef<SavedMessage | null>(null);
  const ports = shallowRef<PortsMessage | null>(null);
  const portsByRadio = shallowRef<ReadonlyMap<number, PortsMessage>>(new Map());
  const updateResult = shallowRef<UpdateResultMessage | null>(null);
  const releaseNotes = shallowRef<ReleaseNotesMessage | null>(null);
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
    packetStats: (message) => (packetStats.value = message),
    speedSeries: (message) => (speedSeriesByCall.value = new Map(speedSeriesByCall.value).set(message.call, message)),
    signalSeries: (message) =>
      (signalSeriesByCall.value = new Map(signalSeriesByCall.value).set(message.call, message)),
    stationTraffic: (message) =>
      (stationTrafficByCall.value = new Map(stationTrafficByCall.value).set(message.call, message)),
    positionHistory: (message) => (positionHistory.value = message),
    alertResult: (message) => (alertResult.value = message),
    saved: (message) => (saved.value = message),
    ports: (message) => {
      ports.value = message;
      if (message.radio !== null) portsByRadio.value = new Map(portsByRadio.value).set(message.radio, message);
    },
    updateResult: (message) => (updateResult.value = message),
    releaseNotes: (message) => (releaseNotes.value = message),
    radioSearch: (message) => (radioSearch.value = message),
  };
  const refs = {
    weatherSeries,
    weatherSeriesByCall,
    packetHistory,
    packetStats,
    packetHistoryByCall,
    speedSeriesByCall,
    signalSeriesByCall,
    stationTrafficByCall,
    positionHistory,
    alertResult,
    saved,
    ports,
    portsByRadio,
    updateResult,
    releaseNotes,
    radioSearch,
  };
  return { ...refs, refs, handlers };
}
