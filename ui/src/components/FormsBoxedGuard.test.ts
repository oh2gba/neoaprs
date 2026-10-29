// A form of fields is a group box (a fieldset with a legend, the look of the Settings groups), on every tab: the one idiom. The forms of the page are the components with a `<form>`; each is listed here with where its box is,
// so that a form added later has to say how it is boxed. The chat line under a conversation (ComposeBar `inline`: one field, the counter and Send) is a line, not a form of fields, and the dialogs (the setup guide, the access key
// gate) are boxes themselves.
import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const COMPONENTS = resolve(__dirname);

const FORMS: Record<string, string> = {
  "ComposeBar.vue": "the box of every form of the Bulletins, Email and Objects tabs: a fieldset with its legend unless it is `inline` (the chat line)",
  "SettingsForm.vue": "the Settings and My station tabs: a fieldset for each group",
  "SetupGuide.vue": "a dialog: the panel is the box, the steps are its pages",
  "KeyScreen.vue": "the gate before the page: one field and its button on the whole screen",
  "StationQuery.vue": "the operator's own query in the station panel of the Stations tab: one field and its button in a line, inside the panel's group box",
};

describe("every form of fields is a group box", () => {
  const forms = readdirSync(COMPONENTS)
    .filter((file) => file.endsWith(".vue") && /<form[\s>]/.test(readFileSync(resolve(COMPONENTS, file), "utf8")))
    .sort();

  it("is known: a component with a <form> says here where its box is", () => {
    expect(forms).toEqual(Object.keys(FORMS).sort());
  });

  it("has a fieldset and a legend in ComposeBar for what is not the chat line, and in SettingsForm", () => {
    const bar = readFileSync(resolve(COMPONENTS, "ComposeBar.vue"), "utf8");
    expect(bar).toMatch(/inline \? 'div' : 'fieldset'/);
    expect(bar).toMatch(/<legend v-if="!inline">/);
    expect(readFileSync(resolve(COMPONENTS, "SettingsForm.vue"), "utf8")).toContain("<fieldset");
  });
});
