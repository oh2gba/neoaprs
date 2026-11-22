import { describe, expect, it } from "vitest";
import { keyLink, login, probe, renewKey, takeKey } from "@/lib/access";
import { FakeFetch } from "@/test/fakefetch";

describe("probe", () => {
  it("says locked for a 401 and open for anything else, even no answer", async () => {
    expect(await probe(new FakeFetch(401).fetch)).toBe("locked");
    expect(await probe(new FakeFetch(204).fetch)).toBe("open");
    expect(await probe(new FakeFetch(404).fetch)).toBe("open");
    expect(await probe(new FakeFetch(0).fetch)).toBe("open");
  });

  it("asks the daemon beside the page, and keeps no answer", async () => {
    const daemon = new FakeFetch(204);
    await probe(daemon.fetch);
    expect(daemon.calls).toEqual([{ url: "http://127.0.0.1:7303/access", method: "GET", body: "", cache: "no-store" }]);
  });
});

describe("login", () => {
  it("sends the key as JSON and is empty when the device is let in", async () => {
    const daemon = new FakeFetch(204);
    expect(await login("k7m2-x9pq-4hrt", daemon.fetch)).toBe("");
    expect(daemon.calls).toHaveLength(1);
    expect(daemon.calls[0]).toMatchObject({ url: "http://127.0.0.1:7303/access", method: "POST" });
    expect(JSON.parse(daemon.calls[0]?.body ?? "")).toEqual({ key: "k7m2-x9pq-4hrt" });
  });

  it("tells a wrong key, too many tries, and no answer, each in a few words", async () => {
    expect(await login("x", new FakeFetch(403).fetch)).toBe("Wrong key.");
    expect(await login("x", new FakeFetch(429).fetch)).toBe("Too many tries. Wait a few minutes.");
    expect(await login("x", new FakeFetch(500).fetch)).toBe("No answer from NeoAPRS.");
    expect(await login("x", new FakeFetch(0).fetch)).toBe("No answer from NeoAPRS.");
  });
});

describe("renewKey", () => {
  it("posts to access/new and is empty when the key was made", async () => {
    const daemon = new FakeFetch(204);
    expect(await renewKey(daemon.fetch)).toBe("");
    expect(daemon.calls).toEqual([{ url: "http://127.0.0.1:7303/access/new", method: "POST", body: "", cache: "no-store" }]);
    expect(await renewKey(new FakeFetch(401).fetch)).toBe("No answer from NeoAPRS.");
  });
});

describe("takeKey", () => {
  /** A place and its history as takeKey sees them, with what it put in the history. */
  function at(href: string) {
    const url = new URL(href);
    const replaced: string[] = [];
    const loc = { hash: url.hash, pathname: url.pathname, search: url.search } as Location;
    const replaceState = (state: unknown, _: string, to: string) => {
      replaced.push(`${JSON.stringify(state)} ${to}`);
      loc.hash = new URL(to, url).hash; // as a browser does: the address is the new one at once
    };
    const hist = { state: { kept: 1 }, replaceState } as unknown as History;
    return { key: takeKey(loc, hist), replaced };
  }

  it("gives the key of #key= and takes the fragment out of the history entry, keeping its path, query and state", () => {
    expect(at("http://192.168.1.20:7303/sub/?lang=fi#key=k7m2-x9pq-4hrt")).toEqual({ key: "k7m2-x9pq-4hrt", replaced: ['{"kept":1} /sub/?lang=fi'] });
  });

  it("decodes an escaped key, and keeps a key with a stray % as it is", () => {
    expect(at("http://h/#key=k7m2%20x9pq%204hrt").key).toBe("k7m2 x9pq 4hrt");
    expect(at("http://h/#key=k7m2%x9pq").key).toBe("k7m2%x9pq");
  });

  it("gives nothing and leaves the address alone for any other fragment, or none", () => {
    for (const href of ["http://h/#app", "http://h/", "http://h/#keys=abc", "http://h/#Key=abc"]) expect(at(href)).toEqual({ key: "", replaced: [] });
  });

  it("takes an empty key out of the address too", () => {
    expect(at("http://h/#key=")).toEqual({ key: "", replaced: ['{"kept":1} /'] });
  });
});

describe("keyLink", () => {
  it("puts the key after #key= at the end of the address, and is empty while either is missing", () => {
    expect(keyLink("http://192.168.1.20:7303/", "k7m2-x9pq-4hrt")).toBe("http://192.168.1.20:7303/#key=k7m2-x9pq-4hrt");
    expect(keyLink("", "k7m2-x9pq-4hrt")).toBe("");
    expect(keyLink("http://192.168.1.20:7303/", "")).toBe("");
  });

  it("writes what takeKey reads back, a key with signs of its own too", () => {
    for (const key of ["k7m2-x9pq-4hrt", "a b#c%d&e"]) {
      const url = new URL(keyLink("https://neoaprs-pi.local:7304/", key));
      const loc = { hash: url.hash, pathname: url.pathname, search: url.search } as Location;
      expect(takeKey(loc, { state: null, replaceState: () => undefined } as unknown as History)).toBe(key);
    }
  });
});
