// The rules of the daemon that are code and not numbers, held to the page's copy:
// ui/src/protocol/vectors.json is written by scripts/gen-protocol.py from the daemon's answers
// (tests/test_vectors.py holds the file to the daemon), and every case is asserted here against the
// page's own function. A rule changed on one side alone fails a test.
import { describe, expect, it } from "vitest";
import { bytesLeft, lockedRoom } from "@/lib/messages";
import { boardKind, canPost, freeSlot, textOk, type PostDraft, type PostKind } from "@/lib/bulletins";
import { isAlias, isMarker } from "@/lib/chain";
import { chatText } from "@/lib/chat";
import { DIAL, pastGroups, postCommand } from "@/lib/skeds";
import { PageErrors } from "@/lib/pageerrors";
import type { PageErrorCommand } from "@/protocol/protocol";
import { pairCall } from "@/lib/settingspair";
import { replyAddressOk } from "@/lib/support";
import { parsePath, validCall, validName } from "@/lib/calls";
import { compareVersions } from "@/lib/releasenotes";
import { callOk, problemOf } from "@/lib/fieldcheck";
import { draftProblems, emptyDraft, nameProblem, objectCommand, qruProblem } from "@/lib/ownobjects";
import vectors from "@/protocol/vectors.json";
import { ownBulletin } from "@/test/fixtures";

describe("the vectors of the daemon", () => {
  it("say which calls a station may transmit under", () => {
    for (const { input, ok } of vectors.calls) expect(callOk(input), JSON.stringify(input)).toBe(ok);
  });

  it("say which addresses for a reply Send logs takes", () => {
    for (const { input, ok } of vectors.reply_addresses) expect(replyAddressOk(input), JSON.stringify(input)).toBe(ok);
  });

  it("say what a line of the chat keeps of its text", () => {
    for (const { input, text } of vectors.chat_texts) expect(chatText(input), JSON.stringify(input)).toBe(text);
  });

  it("are the page_error the page sends at each instant, which the daemon takes", () => {
    for (const { now_ms, command, ok } of vectors.page_error_commands) {
      const sent: PageErrorCommand[] = [];
      const errors = new PageErrors(
        () => now_ms,
        () => command.build,
      );
      errors.attach((built) => sent.push(built) > 0);
      errors.record(command.message, "window");
      expect(sent, String(now_ms)).toEqual([command]);
      expect(ok).toBe(true);
    }
  });

  it("are the sked_post the page sends for each form, which the daemon takes", () => {
    for (const { now_ms, draft, command, ok } of vectors.sked_post_commands) {
      expect(postCommand(draft, now_ms), JSON.stringify(draft)).toEqual(command);
      expect(ok).toBe(true);
    }
  });

  it("say which dials a sked takes", () => {
    for (const { input, ok } of vectors.sked_dials) expect(DIAL.test(input), JSON.stringify(input)).toBe(ok);
  });

  it("say which call a pair of radios gets when its Enable is ticked", () => {
    for (const { station, pairs, pair, ssid } of vectors.pair_calls) {
      const values: Record<string, string> = { "station/call": station };
      for (const [low, high, enabled, stored] of pairs) {
        values[`pair/${String(low)}/${String(high)}/enabled`] = String(enabled);
        values[`pair/${String(low)}/${String(high)}/ssid`] = stored === null ? "" : String(stored);
      }
      const key = `pair/${String(pair[0])}/${String(pair[1])}/ssid`;
      expect(pairCall(key, values), JSON.stringify({ station, pairs })).toBe(`OH2GBA-${String(ssid)}`);
    }
  });

  it("say which skeds are past tests and in which order", () => {
    const now = Date.parse("2026-11-14T12:00:00Z");
    const at = (hours: number) => new Date(now + hours * 3_600_000).toISOString().slice(0, 19) + "Z";
    for (const { skeds, listed } of vectors.sked_past) {
      const rows = skeds.map(([id, call, from, to, dial]) => ({
        id: String(id),
        call: String(call),
        from: at(Number(from)),
        to: at(Number(to)),
        dial: String(dial),
        note: "",
        ours: false,
      }));
      const ids = (found: ReturnType<typeof pastGroups>) => found.flatMap((g) => g.rows.map((r) => r.id));
      expect(ids(pastGroups([], rows, now)), JSON.stringify(skeds)).toEqual(listed);
      expect(
        ids(
          pastGroups(
            rows.filter((r) => Date.parse(r.to) <= now),
            [],
            now,
          ),
        ),
      ).toEqual(listed);
    }
  });

  it("say which calls parse (a path, an addressee), SSID and all", () => {
    for (const { input, ok } of vectors.parse_calls) expect(validCall(input), JSON.stringify(input)).toBe(ok);
  });

  it("say which names a message may be addressed to: a call or a name APRS-IS allows", () => {
    for (const { input, ok } of vectors.station_names) expect(validName(input), JSON.stringify(input)).toBe(ok);
  });

  it("say which paths the daemon takes", () => {
    for (const { input, ok } of vectors.paths) expect(parsePath(input) !== null, JSON.stringify(input)).toBe(ok);
  });

  it("say which texts fit in a message as far as there being a text and its length go", () => {
    for (const { input, ok } of vectors.message_texts)
      expect(input.trim() !== "" && bytesLeft(input) >= 0, JSON.stringify(input)).toBe(ok);
  });

  it("say how many bytes an encrypted message holds where the radio's frame leaves fewer characters", () => {
    for (const { text_max, room } of vectors.locked_rooms) expect(lockedRoom(text_max), String(text_max)).toBe(room);
  });

  it("say which texts can be posted as a bulletin", () => {
    for (const { input, ok } of vectors.bulletin_texts) expect(textOk(input), JSON.stringify(input)).toBe(ok);
  });

  it("say which slot a new post of a kind and a group takes beside the posts of ours", () => {
    for (const { kind, group, taken, slot } of vectors.bulletin_free_slots) {
      const own = new Map(taken.map((s) => [s, ownBulletin(s)]));
      const draft: PostDraft = { kind: kind as PostKind, hours: null, group, text: "Snow" };
      expect(freeSlot(draft.kind, group, own.keys()), JSON.stringify([kind, group, taken])).toBe(slot);
      expect(canPost(draft, own), JSON.stringify([kind, group, taken])).toBe(slot !== null);
    }
  });

  it("say which names an object or an item may have", () => {
    for (const { name, kind, ok } of vectors.object_names) {
      expect(name !== "" && nameProblem(name, kind as "object" | "item") === "", JSON.stringify([kind, name])).toBe(ok);
    }
  });

  it("say which QRU groups an object may be in, and how they are kept", () => {
    for (const { group, ok, kept } of vectors.qru_groups) {
      expect(qruProblem(group) === "", JSON.stringify(group)).toBe(ok);
      if (ok)
        expect(
          objectCommand({ ...emptyDraft(), name: "OBJ", lat: "60.17", lon: "24.94", qru: group }, [1])?.qru_group,
          JSON.stringify(group),
        ).toBe(kept);
    }
  });

  it("say which comments fit an object, alone and behind a course", () => {
    for (const { comment, moving, ok } of vectors.object_comments) {
      const draft = { ...emptyDraft(), name: "OBJ", comment, course: moving ? "90" : "" };
      expect(draftProblems(draft).comment === undefined, JSON.stringify([comment, moving])).toBe(ok);
    }
  });

  it("say which values of the settings the daemon takes, for the settings the page checks", () => {
    for (const { key, input, ok } of vectors.settings)
      expect(problemOf(key, input) === "", JSON.stringify([key, input])).toBe(ok);
  });

  it("say which elements of a path are aliases and which are markers for the iGates", () => {
    for (const { input, alias, marker } of vectors.route_elements) {
      expect(isAlias(input), JSON.stringify(input)).toBe(alias);
      expect(isMarker(input), JSON.stringify(input)).toBe(marker);
    }
  });

  it("say which addressees are the board's and not a station's", () => {
    for (const { input, kind } of vectors.board_names) expect(boardKind(input), JSON.stringify(input)).toBe(kind);
  });

  it("say which of two versions is the newer", () => {
    for (const { a, b, order } of vectors.compare_versions)
      expect(compareVersions(a, b), JSON.stringify([a, b])).toBe(order);
  });
});
