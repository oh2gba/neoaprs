// The calls and frequencies that the pictures show: the same in every language, so that they are data and not words of the page. No real station's call:
// Our own call is YOURCALL (N0CALL, the insiders' word, reads as a real call), and the others carry the ITU Q prefix, which no country has (the same calls as the Dummy radio).
export const CALLS = {
  me: "YOURCALL",
  car: "YOURCALL-9",
  other: "Q1ABC",
  otherCar: "Q1ABC-9",
  digipeater: "Q2DIG-2",
  fillIn: "WIDE1-1",
  wide: "WIDE2-1",
  repeater: "145.600",
  iGateCall: "YOURCALL-10",
  igate: "Q7IGT-1",
  server: "Q1CLB",
  aprsIs: "APRS-IS",
} as const;
