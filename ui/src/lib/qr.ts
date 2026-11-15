// The QR code of a text, for the code a phone's camera opens the page from (components/PhoneCode.vue): the matrix of its modules made by uqr at error correction level M, raised to a higher level where the
// text still fits the same size, with the quiet zone of four modules round it that a reader needs; and one SVG path that draws its dark modules, a run of them in a row as one rectangle. The path is numbers and
// path letters only, so it holds nothing of the text it was made from. The notice of uqr's licence is the legal comment before qrMatrix, code the build keeps, so the built page carries it: uqr's own files have none.
import { encode } from "uqr";

/*! uqr 0.1.3, MIT License, (c) Project Nayuki, (c) 2023 Anthony Fu */
/** The modules of the code of `text`, row by row, the quiet zone included: true is dark. */
export function qrMatrix(text: string): boolean[][] {
  return encode(text, { ecc: "M", boostEcc: true, border: 4 }).data;
}

/** The dark modules of a matrix as one SVG path in a box of `size` by `size` units, one unit a module. */
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
