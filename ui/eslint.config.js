// ESLint for the page: typescript-eslint (recommended, with type information), eslint-plugin-vue (recommended), and the size rules of the project.
// Prettier owns the formatting (eslint-config-prettier switches off what would fight it); `npm run lint` must be clean, no warnings.
import { fileURLToPath } from "node:url";
import js from "@eslint/js";
import prettier from "eslint-config-prettier";
import vue from "eslint-plugin-vue";
import globals from "globals";
import tseslint from "typescript-eslint";
import vueParser from "vue-eslint-parser";

// What a station sends (a comment, a status, a message, a name) is text and must stay text on the page: it reaches the DOM as textContent or through a template's {{ }}, never as markup and never as code.
// v-html is refused by its own rule below; these are the other ways in, refused wherever they are written (the page's code, a template, the service worker). The tests read what a component rendered and keep their use.
// What is only known when the page runs is beyond a rule: an object bound whole (`v-bind="attributes"`) has its keys read where the script writes them, and a name held in a variable (`:[name]="text"`, `element[name] = text`) is read by nothing.
// src/lib/lintrules.test.ts runs these rules on made-up sources, so that a way in that is no longer refused fails a test.
const AS_TEXT = "It would make markup of a text: build the element and set its textContent, or bind the text in the template.";
const HTML_PROPERTIES = ["innerHTML", "outerHTML", "insertAdjacentHTML", "srcdoc", "createContextualFragment", "setHTMLUnsafe"];
const noHtmlProperties = [
  ...HTML_PROPERTIES.map((property) => ({ property, message: AS_TEXT })),
  ...["write", "writeln"].map((property) => ({ object: "document", property, message: AS_TEXT })),
];
// (Vue takes a leading "." off a key and sets the property, and a leading "^" sets the attribute: ".innerHTML" is innerHTML)
const HTML_KEY = `/^[.^]?(${HTML_PROPERTIES.join("|")})$/`;
const noHtmlSyntax = [
  // the same names as the key of an object (h("div", { innerHTML: text }), Object.assign(element, { innerHTML: text }), { [`innerHTML`]: text }) and as an attribute set by name
  {
    selector: `Property[key.name=${HTML_KEY}], Property[key.value=${HTML_KEY}], Property > TemplateLiteral.key > TemplateElement[value.cooked=${HTML_KEY}]`,
    message: AS_TEXT,
  },
  { selector: "CallExpression[callee.property.name=/^setAttribute(NS)?$/] > Literal[value=/^srcdoc$/i]", message: AS_TEXT },
  { selector: "MemberExpression[property.name=/^writeln?$/][object.property.name='document']", message: AS_TEXT },
];
const noHtmlBinding = [{ argument: "/^(inner-?h-?t-?m-?l|outer-?h-?t-?m-?l|srcdoc)$/i", message: AS_TEXT }];
// In a template the plain rules above see nothing, so the same is refused there by the plugin's own rule: the object of a binding (v-bind="{ innerHTML: text }"), a name written between brackets (:[`innerHTML`]="text"),
// which the rule for a binding's name does not read, and a property set or called in a handler (@click="$el.innerHTML = text").
const noHtmlTemplate = [
  ...noHtmlSyntax,
  { selector: "VDirectiveKey > VExpressionContainer TemplateElement[value.cooked=/^(innerHTML|outerHTML|srcdoc)$/i]", message: AS_TEXT },
  {
    selector: `MemberExpression[property.name=${HTML_KEY}], MemberExpression[property.value=${HTML_KEY}], MemberExpression > TemplateLiteral.property > TemplateElement[value.cooked=${HTML_KEY}]`,
    message: AS_TEXT,
  },
];

export default tseslint.config(
  { ignores: ["dist/**", "coverage/**", "node_modules/**", "public/**", "src/protocol/protocol.ts"] },

  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  ...vue.configs["flat/recommended"],

  {
    languageOptions: {
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: fileURLToPath(new URL(".", import.meta.url)),
        extraFileExtensions: [".vue"],
      },
    },
  },
  {
    files: ["**/*.vue"],
    languageOptions: { parser: vueParser, parserOptions: { parser: tseslint.parser, sourceType: "module" } },
  },
  {
    // the config files run in node and are not part of the page's TypeScript project
    files: ["eslint.config.js", "vite.config.ts"],
    ...tseslint.configs.disableTypeChecked,
  },
  { files: ["eslint.config.js", "vite.config.ts"], languageOptions: { globals: globals.node } },
  {
    // the service worker is a plain file of its own (sw/sw.js, written out beside index.html by vite.config.ts), not part of the page's TypeScript project
    files: ["sw/sw.js"],
    ...tseslint.configs.disableTypeChecked,
  },
  { files: ["sw/sw.js"], languageOptions: { globals: globals.serviceworker } },

  {
    rules: {
      "no-console": "warn",
      eqeqeq: ["error", "always", { null: "ignore" }], // `x == null` is the one idiom that stays: null or undefined
      "vue/no-v-html": "error",
      "vue/no-restricted-v-bind": ["error", ...noHtmlBinding],
      // a bare ":" or "." with an object is v-bind of that object, which the template's parser reads as a plain attribute of that name
      "vue/no-restricted-static-attribute": ["error", { key: "srcdoc", message: AS_TEXT }, { key: "/^[:.]$/", message: AS_TEXT }],
      "no-restricted-properties": ["error", ...noHtmlProperties],
      "no-restricted-syntax": ["error", ...noHtmlSyntax],
      "vue/no-restricted-syntax": ["error", ...noHtmlTemplate],
      "no-eval": "error", // text run as code: eval, new Function, and a string given to a timer (which the typed rule of typescript-eslint refuses in the page's own files)
      "no-new-func": "error",
      "vue/block-lang": ["error", { script: { lang: "ts" } }],
      "@typescript-eslint/consistent-type-imports": ["error", { prefer: "type-imports", fixStyle: "inline-type-imports" }],
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],

      // size: a file, a function, the branches of a function. Nothing in ui/src is over these, so there is no allowlist; a function that has to be gets an entry in an
      // `overrides` block below with the reason and the number it may reach, and that number only goes down (a ratchet).
      "max-lines": ["error", { max: 400, skipBlankLines: true, skipComments: true }],
      "max-lines-per-function": ["error", { max: 80, skipBlankLines: true, skipComments: true, IIFEs: true }],
      complexity: ["error", 15],
    },
  },

  {
    // a component is script and template: more than 300 lines of both is two components
    files: ["**/*.vue"],
    rules: {
      "max-lines": ["error", { max: 300, skipBlankLines: true, skipComments: true }],
      "no-restricted-imports": [
        "error",
        { patterns: [{ group: ["./*", "../*"], message: "components, composables and lib are imported by the alias '@/' (@/components/X.vue)" }] },
      ],
    },
  },

  {
    // tests are long by nature: a describe block holds many cases
    files: ["**/*.test.ts", "src/test/**"],
    rules: { "max-lines": "off", "max-lines-per-function": "off", "@typescript-eslint/unbound-method": "off", "vue/one-component-per-file": "off" },
  },
  {
    // a test reads the markup a component made (innerHTML, outerHTML) to say what is on the page, and writes a document of its own to stand a component in; the test of the service worker runs the worker's
    // script as a function, with fakes for a worker's globals. Nothing of a station is shown to anybody
    files: ["**/*.test.ts", "src/test/**"],
    rules: { "no-restricted-properties": "off", "no-restricted-syntax": "off", "no-new-func": "off" },
  },
  {
    // the service worker is linted without type information (above), so the typed rule against a string given to a timer does not see it: the plain one does
    files: ["sw/sw.js"],
    rules: { "no-implied-eval": "error" },
  },

  {
    // a language's catalogue is one file of data with every id of en.ts (docs/development.md, Translations), or one file per area of the page: neither is split by size
    files: ["src/i18n/de.ts", "src/i18n/fr.ts", "src/i18n/*/*.ts"],
    rules: { "max-lines": "off" },
  },

  prettier,
);
