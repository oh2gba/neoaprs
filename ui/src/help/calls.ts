// The calls and frequencies that the pictures show: the same in every language, so that they are data and not words of the page. No real station's call:
// N0CALL is APRS's usual "your call here", and the others carry the ITU Q prefix, which no country has (the same calls as the Dummy radio).
export const CALLS = {
  me: "N0CALL",
  car: "N0CALL-9",
  other: "Q1ABC",
  otherCar: "Q1ABC-9",
  digipeater: "Q2DIG-2",
  fillIn: "WIDE1-1",
  wide: "WIDE2-1",
  repeater: "145.600",
  iGateCall: "N0CALL-10",
  igate: "Q7IGT-1",
  aprsIs: "APRS-IS",
} as const;
