// ESLint for the page: typescript-eslint (recommended, with type information), eslint-plugin-vue (recommended), and the size rules of the project.
// Prettier owns the formatting (eslint-config-prettier switches off what would fight it); `npm run lint` must be clean, no warnings.
import { fileURLToPath } from "node:url";
import js from "@eslint/js";
import prettier from "eslint-config-prettier";
import vue from "eslint-plugin-vue";
import globals from "globals";
import tseslint from "typescript-eslint";
import vueParser from "vue-eslint-parser";

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
    rules: {
      "no-console": "warn",
      eqeqeq: ["error", "always", { null: "ignore" }], // `x == null` is the one idiom that stays: null or undefined
      "vue/no-v-html": "error",
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

  prettier,
);
