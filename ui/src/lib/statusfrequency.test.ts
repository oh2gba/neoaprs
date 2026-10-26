import { describe, expect, it } from "vitest";
import { statusFrequencyHint } from "@/lib/statusfrequency";

describe("the frequency in the status text", () => {
  it("says nothing for a text that starts with the frequency as radios tune to it, with or without what follows", () => {
    for (const text of ["145.500MHz", "145.500MHz QRV", "145.500MHz T088 QRV", "438.925MHz T088 -760 Hello", "145.500MHz, QRV"])
      expect(statusFrequencyHint(text), text).toBeNull();
  });

  it("says how to write the first frequency that is written some other way, or not at the start", () => {
    const cases: [string, string][] = [
      ["QRV 144.800 MHz FM", "144.800MHz"],
      ["QRV 145.500 FM", "145.500MHz"],
      ["144.800 MHz QRV", "144.800MHz"],
      ["145.500mhz QRV", "145.500MHz"],
      ["145.500 MHZ", "145.500MHz"],
      ["Net on 144,800 tonight", "144.800MHz"],
      ["QRV 145.5 MHz", "145.500MHz"],
      ["145.50 simplex", "145.500MHz"],
      ["QRV 28.4 MHz USB", "028.400MHz"],
      [" 145.500MHz QRV", "145.500MHz"],
      ["QRV 145.500MHzX", "145.500MHz"],
      ["QRV 144.800 MHz and 145.500MHz", "144.800MHz"],
    ];
    for (const [text, hint] of cases) expect(statusFrequencyHint(text), text).toBe(hint);
  });

  it("finds nothing in a text without a frequency: a time, a version, a count, a tone, an offset", () => {
    for (const text of ["", "At the summer cottage", "Home until 12.30", "v2.5.1 running", "QRV T088 -060", "100 stations, 3.5 W", "temp 21.5 C", "a1145.500b"])
      expect(statusFrequencyHint(text), text).toBeNull();
  });
});
