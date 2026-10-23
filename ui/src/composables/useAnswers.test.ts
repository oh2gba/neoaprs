import { describe, expect, it } from "vitest";
import { useAnswers } from "@/composables/useAnswers";
import { series } from "@/test/fixtures";

describe("useAnswers: the weather series", () => {
  it("keeps the latest answer, and the latest of each station, so that several weather cards each have their graphs", () => {
    const answers = useAnswers();
    answers.handlers.weatherSeries(series("OH2ZWA", 24, 3));
    answers.handlers.weatherSeries(series("OH2ZWB", 24, 4));
    expect(answers.weatherSeries.value?.call).toBe("OH2ZWB");
    expect([...answers.weatherSeriesByCall.value.keys()]).toEqual(["OH2ZWA", "OH2ZWB"]);
    const again = series("OH2ZWA", 168, 5);
    answers.handlers.weatherSeries(again);
    expect(answers.weatherSeriesByCall.value.get("OH2ZWA")).toBe(again);
    expect(answers.weatherSeriesByCall.value.get("OH2ZWB")?.points).toHaveLength(4);
  });
});
