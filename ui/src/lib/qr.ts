// The QR code of a text, for the code a phone camera opens the page from
// (components/PhoneCode.vue):
// the module matrix made by uqr at error correction level M, raised where the text still fits the
// same size, with a four-module quiet zone; and one SVG path of the dark modules (runs in a row as
// one rectangle). The path holds only numbers and path letters, nothing of the text. uqr's licence
// notice is the legal comment before qrMatrix, which the build keeps.
import { encode } from "uqr";

/*! uqr 0.1.3, MIT License, (c) Project Nayuki, (c) 2023 Anthony Fu */
/** The modules of the code of `text`, row by row, quiet zone included: true is dark. */
export function qrMatrix(text: string): boolean[][] {
  return encode(text, { ecc: "M", boostEcc: true, border: 4 }).data;
}

/** The dark modules as one SVG path in a `size` by `size` box, one unit per module. */
export function qrPath(matrix: readonly (readonly boolean[])[]): { size: number; d: string } {
  const parts: string[] = [];
  matrix.forEach((row, y) => {
    for (let x = 0; x < row.length; x++) {
      if (!row[x]) continue;
      const start = x;
      while (row[x + 1]) x++;
      const run = x - start + 1;
      parts.push(`M${start} ${y}h${run}v1h-${run}z`);
    }
  });
  return { size: matrix.length, d: parts.join("") };
}
