// Which shape an aircraft is drawn with (lib/layers/aircraftshapes.ts). First by emitter category
// (`category`: A1 light to A7 rotorcraft, B1 glider to B6 unmanned; the C ones, on the ground,
// never reach the page). Where the category says only the weight (A1 to A5) or nothing, by ICAO
// type designator (`designator`: `R44`, `A388`) against a short list from ICAO's public designators
// (Doc 8643). An aircraft of which nothing is known gets the general shape.
import type { AircraftShape } from "@/lib/layers/aircraftshapes";

/** The shape of each emitter category that names a kind or a weight. */
const BY_CATEGORY: Readonly<Record<string, AircraftShape>> = {
  A1: "light", // light, under 7 t
  A2: "twin", // small, 7 to 34 t
  A3: "airliner", // large, 34 to 136 t
  A4: "airliner", // high vortex large (the B757)
  A5: "heavy", // heavy, over 136 t
  A6: "bizjet", // high performance, over 5 g and 400 knots
  A7: "helicopter", // rotorcraft
  B1: "glider", // glider or sailplane
  B2: "balloon", // lighter than air
  B3: "unknown", // parachutist
  B4: "light", // ultralight, hang glider, paraglider
  B6: "drone", // unmanned
};

/** The categories that say only how heavy an aircraft is; its type designator may say more. */
const WEIGHT_ONLY = new Set(["", "A1", "A2", "A3", "A4", "A5"]);

/**
 * The type designators that name the kind, in the order tried; a dot matches any one letter or
 * digit.
 */
const BY_DESIGNATOR: readonly (readonly [AircraftShape, RegExp])[] = [
  [
    "helicopter",
    /^(H\d{2,3}|EC\d\d|AS32|AS3B|AS50|AS55|AS65|R22|R44|R66|B06|B407|B412|B429|A109|A119|A139|A169|A189|S76|S92|NH90|EH10|BK17|EXPL|GAZL|PUMA|LYNX|MI8|MI24|UH1)$/,
  ],
  ["glider", /^(GLID|DUOD|DISC|VENT|NIMB|JANU)$/],
  ["balloon", /^BALL$/],
  ["drone", /^(Q1|Q4|Q9)$/],
  ["heavy4", /^(A38.|B74.|A34.|A124|A225|IL76|IL96|C5M|C17|B52|K35R|E3TF|E3CF)$/],
  ["heavy", /^(B76.|B77.|B78.|A30.|A310|A33.|A35.|MD11)$/],
  ["airliner", /^(A31.|A32.|A2.N|B71.|B72.|B73.|B3.M|B75.|BCS1|BCS3|CRJ.|E17.|E19.|E29.|E75.|MD8.|MD90|SU95|C919)$/],
  [
    "bizjet",
    /^(C25.|C5..|C68A|C700|C750|GLF.|GL5T|GL7T|GLEX|F2TH|F900|FA7X|FA8X|LJ..|CL30|CL35|CL60|E50P|E55P|H25.|PRM1|HDJT|PC24)$/,
  ],
  [
    "twin",
    /^(AT4.|AT7.|DH8.|SF34|JS31|JS32|JS41|B190|BE20|BE30|BE9L|DHC6|D228|L410|P68|DA42|DA62|PA31|PA34|PA44|C310|C340|BE55|BE58)$/,
  ],
  ["light", /^(C15.|C17.|C18.|C20.|C21.|P28.|PA18|PA38|SR20|SR22|DA20|DA40|BE33|BE35|BE36|M20P|PC12|C208|TBM.)$/],
];

/** The shape for an emitter category and a type designator (both upper case, "" when unknown). */
export function aircraftShape(category: string, designator: string): AircraftShape {
  const kind = BY_CATEGORY[category];
  if (kind !== undefined && !WEIGHT_ONLY.has(category)) return kind;
  const byType = designator === "" ? undefined : BY_DESIGNATOR.find(([, pattern]) => pattern.test(designator))?.[0];
  return byType ?? kind ?? "unknown";
}
