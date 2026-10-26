// The frequency in the text of our status report, the APRS way (the specification's chapter on the frequency, section 13 of the notes): a radio tunes to the voice frequency when the text starts with it as `FFF.FFFMHz` (`145.500MHz`, and
// after it ` T088`, ` -060` and the like). This finds the first frequency that is written some other way (`QRV 144.800 MHz FM`, `144.800 MHz`, `145.500mhz`) so that the Text field can say, quietly, how to write it. It blocks nothing.

/** The form a radio tunes to, at the start of the text: three digits, a point, three digits and `MHz` as written here. */
const IN_FORM = /^\d{3}\.\d{3}MHz(?![A-Za-z])/;
/** A number that looks like a frequency: with `MHz` after it (also with a blank between) two or three digits before the point and up to three after, else three before and two or three after (`144.800`), so that a time or a version number is none. */
const FREQUENCY = /(?<![\w.,])(\d{2,3})[.,](\d{1,3})(?!\d)(\s?mhz\b)?/gi;

/** The form to write the first frequency of the text in (`144.800MHz`) when it is not at the start of the text in that form, else null: no frequency in the text, or the text starts with one as radios read it. */
export function statusFrequencyHint(text: string): string | null {
  if (IN_FORM.test(text)) return null;
  for (const found of text.matchAll(FREQUENCY)) {
    const [, whole = "", decimals = "", unit] = found;
    if (unit === undefined && (whole.length !== 3 || decimals.length < 2)) continue;
    return `${whole.padStart(3, "0")}.${decimals.padEnd(3, "0")}MHz`;
  }
  return null;
}
