// The pictures of the (i) notes (help/): one name for each, which is also the end of the id of its description (`help.picture.<name>`, the alt text).
export const PICTURE_NAMES = [
  "object",
  "bulletin",
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
  "transmit",
  "beaconoff",
  "internet",
  "channels",
  "dummy",
  "notifications",
] as const;

export type PictureName = (typeof PICTURE_NAMES)[number];
