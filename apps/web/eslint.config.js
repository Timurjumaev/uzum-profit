import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "src/lib/api/schema.d.ts"] }, // schema.d.ts — generatsiya (pnpm api:types)
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: { globals: globals.browser },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Formatlash faqat lib/format orqali (03 §9, 04 §8.4).
      "no-restricted-syntax": [
        "error",
        {
          selector: "CallExpression[callee.property.name=/^toLocale(String|DateString|TimeString)$/]",
          message: "Formatlash faqat lib/format orqali (04 §8.4).",
        },
        {
          selector: "MemberExpression[object.name='Intl']",
          message: "Formatlash faqat lib/format orqali (04 §8.4).",
        },
      ],
    },
  },
);
