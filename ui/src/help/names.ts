// The (i) note pictures (help/): one name each, also the end of the id of its description
// (`help.picture.<name>`, the alt text).
export const PICTURE_NAMES = [
  "object",
  "bulletin",
  "bulletingroup",
  "beacon",
  "path",
  "status",
  "range",
  "request",
  "ssid",
  "symbol",
  "network",
  "accesskey",
  "igate",
  "radius",
  "position",
  "digipeater",
  "logs",
  "beaconoff",
  "internet",
  "channels",
  "dummy",
  "notifications",
  "qru",
  "encrypt",
  "mercury",
  "scope",
  "tworadios",
  "gated",
] as const;

export type PictureName = (typeof PICTURE_NAMES)[number];
