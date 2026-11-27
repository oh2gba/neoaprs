// Every outside address the page links to is in lib/links.ts, so that the gate's links stage
// (scripts/linkcheck.py) asks each of them: no other source file of the page holds one.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import * as links from "@/lib/links";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..");
/** Not a link: the SVG namespace, the loopback, the made-up hosts of examples, and an address made
 * of the station's own name. */
const NOT_A_LINK = /^https?:\/\/(www\.w3\.org\/|localhost|127\.0\.0\.1|\[::1\]|[^/]*\.local\b|[^/]*example)/;
const ADDRESS = /https?:\/\/[^\s"'`)<>\\]+/g;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : [path];
  });
}

/** The text without its comments (an address in a comment says where something came from). */
const code = (text: string): string => text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/[^\n]*/g, "$1");

describe("the page's outside links", () => {
  it("are all in lib/links.ts", () => {
    const strays = files(SRC)
      .map((path) => relative(SRC, path).replaceAll("\\", "/"))
      .filter((name) => /\.(ts|vue)$/.test(name) && !/\.test\.ts$/.test(name) && !name.startsWith("test/"))
      .filter((name) => name !== "lib/links.ts")
      .flatMap((name) =>
        [...code(readFileSync(join(SRC, name), "utf-8")).matchAll(ADDRESS)]
          .map((m) => m[0])
          .filter((address) => !NOT_A_LINK.test(address) && !address.includes("${"))
          .map((address) => `${name}: ${address}`),
      );
    expect(strays).toEqual([]);
  });

  it("are https addresses of a host", () => {
    for (const [name, url] of Object.entries(links)) {
      expect(new URL(url).protocol, name).toBe("https:");
      expect(new URL(url).hostname, name).toContain(".");
    }
  });
});
