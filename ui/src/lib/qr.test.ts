// The code a phone's camera reads: uqr's matrix is module for module the symbol Project Nayuki's own encoder makes for the same text (qr.fixture.json, made with its Python port qrcodegen 1.8.0 at level M,
// boosted, its own mask) inside a quiet zone of four light modules, for the shortest address with a key, the longest IPv4 one over https, a 63-letter .local name, and the address the screenshots show; and the
// path draws exactly the dark modules, with nothing in it but numbers and path letters.
import { describe, expect, it } from "vitest";
import fixture from "@/lib/qr.fixture.json";
import { qrMatrix, qrPath } from "@/lib/qr";

type Golden = { text: string; version: number; ecc: string; mask: number; rows: string[] };
const GOLDENS = Object.entries(fixture).filter((entry): entry is [string, Golden] => typeof entry[1] === "object");
const QUIET = 4;

/** The matrix the path draws, read back from its rectangles. */
function drawn(size: number, d: string): boolean[][] {
  const out = Array.from({ length: size }, () => new Array<boolean>(size).fill(false));
  for (const m of d.matchAll(/M(\d+) (\d+)h(\d+)v1h-(\d+)z/g)) {
    const [x, y, run, back] = [m[1], m[2], m[3], m[4]].map(Number);
    expect(back).toBe(run);
    for (let i = 0; i < run; i++) out[y][x + i] = true;
  }
  return out;
}

describe("qrMatrix", () => {
  it("holds the four golden codes, of every size the page can be asked for", () => {
    expect(GOLDENS.map(([name]) => name)).toEqual(["short", "longest_ipv4", "longest_local", "shown"]);
    expect(GOLDENS.map(([, g]) => g.version)).toEqual([3, 4, 6, 4]);
    expect(new TextEncoder().encode(fixture.longest_local.text).length).toBeGreaterThan(100);
  });

  it.each(GOLDENS)("makes %s module for module as Nayuki's encoder, inside a quiet zone of four light modules", (_, golden) => {
    const matrix = qrMatrix(golden.text);
    const n = golden.rows.length;
    expect(n).toBe(golden.version * 4 + 17);
    expect(matrix).toHaveLength(n + 2 * QUIET);
    expect(matrix.every((row) => row.length === n + 2 * QUIET)).toBe(true);
    const inner = matrix.slice(QUIET, QUIET + n).map((row) =>
      row
        .slice(QUIET, QUIET + n)
        .map((dark) => (dark ? "1" : "0"))
        .join(""),
    );
    expect(inner).toEqual(golden.rows);
    const quiet = matrix.flatMap((row, y) => row.filter((dark, x) => dark && (y < QUIET || y >= QUIET + n || x < QUIET || x >= QUIET + n)));
    expect(quiet).toEqual([]);
  });
});

describe("qrPath", () => {
  it.each(GOLDENS)("draws the dark modules of %s and nothing else, in a box of the matrix's size", (_, golden) => {
    const matrix = qrMatrix(golden.text);
    const { size, d } = qrPath(matrix);
    expect(size).toBe(matrix.length);
    expect(drawn(size, d)).toEqual(matrix);
  });

  it("holds only numbers and path letters, and nothing of the address or the key", () => {
    const { d } = qrPath(qrMatrix(fixture.shown.text));
    expect(d).toMatch(/^(M\d+ \d+h\d+v1h-\d+z)+$/);
    expect(d).not.toContain("192");
    expect(d).not.toContain("k7m2");
  });

  it("draws a run of dark modules in a row as one rectangle", () => {
    expect(
      qrPath([
        [true, true, false],
        [false, true, true],
        [true, false, true],
      ]),
    ).toEqual({ size: 3, d: "M0 0h2v1h-2zM1 1h2v1h-2zM0 2h1v1h-1zM2 2h1v1h-1z" });
  });
});
