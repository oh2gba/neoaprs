// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { weather as source } from "@/i18n/en/weather";
import type { Message } from "@/i18n/message";

export const weather: Record<keyof typeof source, Message> = {
  "weather.label": "Tempo",
  "weather.temperature": "Temperatura",
  "weather.wind": "Vento",
  "weather.wind_from": "de {bearing}",
  "weather.gusts": "rajadas {speed}",
  "weather.humidity": "Umidade",
  "weather.pressure": "Pressão",
  "weather.rain_1h": "Chuva 1 h",
  "weather.rain_24h": "Chuva 24 h",
  "weather.rain_today": "Chuva hoje",
  "weather.light": "Luminosidade",
  "weather.snow_24h": "Neve 24 h",
  "weather.none": "Nenhum relatório meteorológico recebido ainda.",
  "weather.period": "Período dos gráficos",
  "weather.span.days": { one: "{n} dia", other: "{n} dias" },
  "weather.loading": "Carregando as observações…",
  "weather.no_observations": "Nenhuma observação neste período.",
  "weather.chart.wind": "Vento e rajadas",
  "weather.chart.rain": "Chuva, última hora",
  "weather.chart.label": "{title}, {unit}",
};
