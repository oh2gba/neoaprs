// The rules of the daemon that are code and not numbers, held to the page's copy of them: ui/src/protocol/vectors.json is written by scripts/gen-protocol.py from what the daemon's Python answers for each input
// (tests/test_vectors.py holds the file to the daemon), and every case is asserted here against the page's own function. A rule changed on one side alone fails a test on that side.
import { describe, expect, it } from "vitest";
import { bytesLeft } from "@/lib/messages";
import { canPost, postCommand, textOk, type PostDraft } from "@/lib/bulletins";
import { parsePath, validCall } from "@/lib/calls";
import { callOk, problemOf } from "@/lib/fieldcheck";
import { draftProblems, emptyDraft, nameProblem, objectCommand, qruProblem } from "@/lib/ownobjects";
import vectors from "@/protocol/vectors.json";

describe("the vectors of the daemon", () => {
  it("say which calls a station may transmit under", () => {
    for (const { input, ok } of vectors.calls) expect(callOk(input), JSON.stringify(input)).toBe(ok);
  });

  it("say which calls parse (a path, an addressee), SSID and all", () => {
    for (const { input, ok } of vectors.parse_calls) expect(validCall(input), JSON.stringify(input)).toBe(ok);
  });

  it("say which paths the daemon takes", () => {
    for (const { input, ok } of vectors.paths) expect(parsePath(input) !== null, JSON.stringify(input)).toBe(ok);
  });

  it("say which texts fit in a message as far as there being a text and its length go", () => {
    for (const { input, ok } of vectors.message_texts) expect(input.trim() !== "" && bytesLeft(input) >= 0, JSON.stringify(input)).toBe(ok);
  });

  it("say which texts can be posted as a bulletin", () => {
    for (const { input, ok } of vectors.bulletin_texts) expect(textOk(input), JSON.stringify(input)).toBe(ok);
  });

  it("say which slot a bulletin of a kind, an identifier and a group is posted to", () => {
    for (const { kind, id, group, slot } of vectors.bulletin_slots) {
      const draft: PostDraft = { kind: kind as PostDraft["kind"], id, group, text: "Snow" };
      expect(postCommand(draft)?.slot ?? null, JSON.stringify([kind, id, group])).toBe(slot);
      expect(canPost(draft)).toBe(slot !== null);
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
      if (ok) expect(objectCommand({ ...emptyDraft({ lat: 60.17, lon: 24.94 }), name: "OBJ", qru: group })?.qru_group, JSON.stringify(group)).toBe(kept);
    }
  });

  it("say which comments fit an object, alone and behind a course", () => {
    for (const { comment, moving, ok } of vectors.object_comments) {
      const draft = { ...emptyDraft({ lat: 60.17, lon: 24.94 }), name: "OBJ", comment, course: moving ? "90" : "" };
      expect(draftProblems(draft).comment === undefined, JSON.stringify([comment, moving])).toBe(ok);
    }
  });

  it("say which values of the settings the daemon takes, for the settings the page checks", () => {
    for (const { key, input, ok } of vectors.settings) expect(problemOf(key, input) === "", JSON.stringify([key, input])).toBe(ok);
  });
});
