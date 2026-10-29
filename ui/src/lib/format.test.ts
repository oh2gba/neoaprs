import { describe, expect, it } from "vitest";
import { setLocale } from "@/i18n";
import {
  agoWords,
  ageSeconds,
  ageText,
  bearingText,
  bearingTitle,
  bytesText,
  clockText,
  compassPoint,
  dateTimeText,
  distanceText,
  hourMinuteText,
  pad2,
  pathText,
  positionText,
  processText,
  silentText,
  speedText,
  untilText,
} from "@/lib/format";
import { NOW, ago } from "@/test/fixtures";

describe("untilText", () => {
  const later = (s: number): string => new Date(NOW + s * 1000).toISOString();
  it("counts seconds, minutes, hours and days ahead, rounding up", () => {
    expect(untilText(later(12), NOW)).toBe("in 12 s");
    expect(untilText(later(61), NOW)).toBe("in 2 min");
    expect(untilText(later(3600 + 1), NOW)).toBe("in 2 h");
    expect(untilText(later(2 * 86400), NOW)).toBe("in 2 d");
  });
  it("is now for a time that has come, and a dash for none", () => {
    expect(untilText(later(0), NOW)).toBe("now");
    expect(untilText(later(-30), NOW)).toBe("now");
    expect(untilText(null, NOW)).toBe("-");
  });
});

describe("silentText", () => {
  it("says since when in the viewer's time and how long ago", () => {
    expect(silentText(ago(5 * 3600 + 100), NOW)).toMatch(/^nothing heard since \d\d:\d\d \(5 h\)$/);
    expect(silentText(ago(17 * 60), NOW)).toMatch(/\(17 min\)$/);
  });
  it("says only that nothing was heard when the time is not known", () => {
    expect(silentText(null, NOW)).toBe("nothing heard");
  });
});

describe("ageText", () => {
  it("counts seconds, minutes, hours and days", () => {
    expect(ageText(ago(12), NOW)).toBe("12 s");
    expect(ageText(ago(3 * 60 + 20), NOW)).toBe("3 min");
    expect(ageText(ago(5 * 3600 + 100), NOW)).toBe("5 h");
    expect(ageText(ago(2 * 86400 + 5), NOW)).toBe("2 d");
  });
  it("is a dash for no time and zero for a time in the future", () => {
    expect(ageText(null, NOW)).toBe("-");
    expect(ageText("not a time", NOW)).toBe("-");
    expect(ageText(ago(-30), NOW)).toBe("0 s");
  });
  it("has the age in seconds, infinite for none", () => {
    expect(ageSeconds(ago(90), NOW)).toBe(90);
    expect(ageSeconds(null, NOW)).toBe(Infinity);
  });
});

describe("numbers", () => {
  it("writes a distance with a decimal under ten", () => {
    expect(distanceText(0.74)).toBe("0.7");
    expect(distanceText(25.4)).toBe("25");
    expect(distanceText(null)).toBe("-");
    expect(distanceText(9.96)).toBe("10");
    expect(distanceText(9.94)).toBe("9.9");
    expect(distanceText(10.4)).toBe("10");
  });
  it("names the compass point of a bearing", () => {
    expect(compassPoint(0)).toBe("N");
    expect(compassPoint(258)).toBe("WSW");
    expect(compassPoint(259)).toBe("W");
    expect(compassPoint(359)).toBe("N");
    expect(compassPoint(-90)).toBe("W");
    expect(bearingText(150)).toBe("150° SSE");
    expect(bearingText(null)).toBe("-");
    expect(bearingText(359.6)).toBe("0° N");
    expect(bearingText(359.4)).toBe("359° N");
    expect(bearingTitle(359.6)).toBe("N, 0°");
  });
  it("writes a position with the hemispheres", () => {
    expect(positionText(60.17, 24.94)).toBe("60.17000 N 24.94000 E");
    expect(positionText(-33.5, -70.25)).toBe("33.50000 S 70.25000 W");
    expect(positionText(null, 24)).toBe("-");
    expect(positionText(60.42951, 24.14519, 4)).toBe("60.4295 N 24.1452 E");
  });
  it("writes speed, path and bytes", () => {
    expect(speedText(12.6)).toBe("13 km/h");
    expect(pathText(["A*", "B"])).toBe("A*,B");
    expect(pathText([])).toBe("-");
    expect(bytesText(512)).toBe("512 B");
    expect(bytesText(2048)).toBe("2.0 kB");
    expect(bytesText(3 * 1024 * 1024)).toBe("3.0 MB");
  });
});

describe("times", () => {
  it("writes a time of the wire in the viewer's time", () => {
    const iso = "2026-10-21T12:34:56Z";
    const d = new Date(iso);
    expect(clockText(iso)).toBe(`${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`);
    expect(hourMinuteText(iso)).toBe(clockText(iso).slice(0, 5));
    expect(hourMinuteText("nope")).toBe("-");
    expect([pad2(0), pad2(7), pad2(31)]).toEqual(["00", "07", "31"]);
    expect(dateTimeText(iso)).toContain(String(d.getFullYear()));
    expect(dateTimeText(null)).toBe("-");
    expect(clockText("nope")).toBe("-");
  });
});

describe("processText", () => {
  it("says in a sentence the share of a core, the memory and the time up, in the units of the page", () => {
    expect(processText(0.3, 42.4, 3 * 3600 + 120)).toBe("NeoAPRS uses 0.3 % of one processor core and 42 MB of memory, running for 3 h");
    expect(processText(12, 100.6, 45)).toBe("NeoAPRS uses 12.0 % of one processor core and 101 MB of memory, running for 45 s");
    expect(processText(1.25, 9, 3 * 86400)).toBe("NeoAPRS uses 1.3 % of one processor core and 9 MB of memory, running for 3 d");
  });
  it("does not count a negative time up", () => {
    expect(processText(0, 9, -5)).toBe("NeoAPRS uses 0.0 % of one processor core and 9 MB of memory, running for 0 s");
  });
  it("leaves the memory out when it is not known", () => {
    expect(processText(0.3, null, 90)).toBe("NeoAPRS uses 0.3 % of one processor core, running for 1 min");
  });
});

describe("the numbers and words of another language", () => {
  it("write the decimal point of the language and the words of its catalogue", () => {
    setLocale("de");
    expect(positionText(60.17, -24.94)).toBe("60,17000 N 24,94000 W");
    expect(distanceText(1.25)).toBe("1,3");
    expect(bytesText(1536)).toBe("1,5 kB");
    expect(agoWords(ago(120), NOW)).toBe("vor 2 min");
    expect(ageText(ago(7200), NOW)).toBe("2 h");
    expect(processText(0.3, 56.4, 3 * 3600)).toBe("NeoAPRS belegt 0,3 % eines Prozessorkerns und 56 MB Arbeitsspeicher, in Betrieb seit 3 h");
  });
  it("says the sentence in every language, with the number written as the language writes it", () => {
    const said: Record<string, string> = {
      fr: "NeoAPRS utilise 0,3 % d'un cœur de processeur et 56 MB de mémoire, en marche depuis 3 h",
      es: "NeoAPRS usa el 0,3 % de un núcleo del procesador y 56 MB de memoria, y lleva 3 h en marcha",
      it: "NeoAPRS usa il 0,3 % di un core del processore e 56 MB di memoria, in funzione da 3 h",
      ja: "NeoAPRSはプロセッサコア1つの0.3 %と56 MBのメモリを使用しています。稼働時間: 3時間",
      "pt-BR": "O NeoAPRS usa 0,3 % de um núcleo do processador e 56 MB de memória, em execução há 3 h",
    };
    for (const [language, text] of Object.entries(said)) {
      setLocale(language);
      expect(processText(0.3, 56.4, 3 * 3600)).toBe(text);
      expect(processText(0.3, null, 3 * 3600)).not.toContain("MB");
    }
  });
});
