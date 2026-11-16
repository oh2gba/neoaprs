// The codes the daemon sends in place of a sentence (a reason, a state's why, a kind of packet, an area's shape and colour: the enums of ui/src/protocol/schema.json, written from the daemon's wire models) each
// have the page's words, in every language of the page: no code falls back to the plain words of its place, and none is shown as the code itself. A code the daemon gains fails here until the page says it.
import { afterEach, describe, expect, it } from "vitest";
import { setLocale, t } from "@/i18n";
import { LOCALES } from "@/i18n/locales";
import { errorReason } from "@/i18n/errortext";
import { outcomeOf } from "@/composables/useUpdateCheck";
import { outcomeText } from "@/composables/useAlertTest";
import { areaWords } from "@/lib/details";
import { gpsProblem } from "@/lib/gpsstatus";
import { reasonText } from "@/lib/httpshelp";
import { igateLook } from "@/lib/igatestatus";
import { blockedText, problemText } from "@/lib/mapfetch";
import { packetFacts } from "@/lib/packetview";
import { gpsState, igateState, mapState, packet } from "@/test/fixtures";
import schema from "@/protocol/schema.json";
import errors from "@/protocol/errors.json";
import type {
  AlertResultMessage,
  AreaValues,
  DecodedOther,
  DecodedUndecoded,
  GpsState,
  HttpsState,
  IgateState,
  MapState,
  PacketRow,
  UpdateResultMessage,
} from "@/protocol/protocol";

interface Property {
  enum?: string[];
}
const DEFS = (schema as unknown as { $defs: Record<string, { properties: Record<string, Property> }> }).$defs;

/** The codes of a field of a model, as the schema lists them; empty is no code (all is well). */
function codes(model: string, field: string): string[] {
  const found = DEFS[model]?.properties[field]?.enum;
  if (found === undefined) throw new Error(`${model}.${field} is not an enum of the schema`);
  return found.filter((code) => code !== "");
}

const kindOf = (row: PacketRow): string => packetFacts(row).find((fact) => fact.label === t("packets.fact.kind"))?.text ?? "";
const whyOf = (row: PacketRow): string => packetFacts(row).find((fact) => fact.label === t("packets.fact.why"))?.text ?? "";

/** Each field: its codes, the page's words for one, and the plain words of the place, which a code the page has no words for falls back to. */
const SAID: Record<string, { codes: () => string[]; say: (code: string) => string; plain: () => string }> = {
  "GpsState.reason": {
    codes: () => codes("GpsState", "reason"),
    say: (c) => gpsProblem(gpsState({ state: "connecting", reason: c as GpsState["reason"] })),
    plain: () => "",
  },
  "IgateState.reason": {
    codes: () => codes("IgateState", "reason").filter((c) => c !== "unverified"), // (the state `unverified` has a line of its own: the reason is not said for it)
    say: (c) => igateLook(igateState({ enabled: true, state: "connecting", reason: c as IgateState["reason"] }), {}, 0).line,
    plain: () => t("settings.tnc.not_connected"),
  },
  "HttpsState.reason": { codes: () => codes("HttpsState", "reason"), say: (c) => reasonText(c as HttpsState["reason"]), plain: () => "" },
  "MapProblem.code": {
    codes: () => codes("MapProblem", "code"),
    say: (c) =>
      problemText(mapState({ state: "error", problem: { code: c as NonNullable<MapState["problem"]>["code"], params: { days: 10, size: 900, max: 800 } } })),
    plain: () => "",
  },
  "MapState.blocked": { codes: () => codes("MapState", "blocked"), say: (c) => blockedText(mapState({ blocked: c as MapState["blocked"] })), plain: () => "" },
  "UpdateResultMsg.reason": {
    codes: () => codes("UpdateResultMsg", "reason"),
    say: (c) => outcomeOf({ type: "update_result", outcome: "no_answer", version: "", reason: c as UpdateResultMessage["reason"] }).text,
    plain: () => t("settings.update.no_answer"),
  },
  "AlertResultMsg.outcome": {
    codes: () => codes("AlertResultMsg", "outcome"),
    say: (c) => outcomeText({ type: "alert_result", ok: c === "ran", outcome: c as AlertResultMessage["outcome"], status: 3, seconds: 20, line: "" }),
    plain: () => "",
  },
  "DecodedUndecoded.code": {
    codes: () => codes("DecodedUndecoded", "code").filter((c) => c !== "damaged"), // (the plain word of the place itself)
    say: (c) => whyOf(packet(1, { kind: "undecoded", decoded: { type: "undecoded", code: c as DecodedUndecoded["code"], text: "!60" } })),
    plain: () => t("packets.why.damaged"),
  },
  "DecodedOther.kind": {
    codes: () => codes("DecodedOther", "kind").filter((c) => c !== "unknown"), // (the plain "Other packet" itself)
    say: (c) =>
      kindOf(packet(1, { kind: "other", decoded: { type: "other", kind: c as DecodedOther["kind"], text: "", weather: null, items: null, timestamp: null } })),
    plain: () => t("packets.kind.other"),
  },
  "AreaValues.shape": {
    codes: () => codes("AreaValues", "shape"),
    say: (c) => areaWords({ shape: c as AreaValues["shape"], colour: "red" }).shape,
    plain: () => "",
  },
  "AreaValues.colour": {
    codes: () => codes("AreaValues", "colour"),
    say: (c) => areaWords({ shape: "line", colour: c as AreaValues["colour"] }).colour,
    plain: () => "",
  },
};

afterEach(() => setLocale("en"));

describe("the codes the daemon sends in place of a sentence", () => {
  for (const [field, { codes: of, say, plain }] of Object.entries(SAID))
    it(`${field}: each has the page's words in every language`, () => {
      expect(of().length).toBeGreaterThan(0);
      for (const locale of LOCALES) {
        setLocale(locale.code);
        for (const code of of()) {
          const said = say(code);
          expect(said, `${locale.code} ${field} ${code}`).not.toBe("");
          expect(said, `${locale.code} ${field} ${code}: the plain words of the place`).not.toBe(plain());
          if (/[._]/.test(code)) expect(said, `${locale.code} ${field} ${code}: the code itself`).not.toContain(code);
        }
      }
    });

  it("and a code the page does not know (a daemon of another build, which the page meets until it has loaded again) is said without throwing, never as the code and never as a placeholder", () => {
    for (const [field, { say }] of Object.entries(SAID))
      for (const code of ["zz_newer", undefined as unknown as string]) {
        let said = "";
        expect(() => (said = say(code)), `${field} ${code}`).not.toThrow();
        expect(said, `${field} ${code}`).not.toContain("zz_newer");
        expect(said, `${field} ${code}`).not.toMatch(/\{\w+\}|undefined/);
      }
  });

  it("and every refusal the daemon codes has its sentence in every language", () => {
    const failed = (): string => t("error.failed");
    const coded = Object.keys(errors).filter((code) => !["failed", "not_json", "topic.unknown"].includes(code));
    for (const locale of LOCALES) {
      setLocale(locale.code);
      for (const code of coded) expect(errorReason({ cmd: "", key: null, code, params: {}, text: "" }), `${locale.code} ${code}`).not.toBe(failed());
    }
  });
});
