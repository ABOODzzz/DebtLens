---
name: DebtLens i18n architecture
description: How Arabic/English language support is implemented in DebtLens (artifacts/debt-lens), for future i18n-related work.
---

DebtLens ships a custom, dependency-free i18n layer (no i18next):

- `src/lib/i18n/context.tsx` — `LanguageProvider` + `useLanguage()` returning `{ language, dir, t, setLanguage, toggleLanguage }`. Persists to localStorage, syncs `document.documentElement.lang`/`dir`. Arabic is the default language.
- `src/lib/i18n/translations.ts` — aggregator merging per-page dictionaries (`src/lib/i18n/dictionaries/<page>.ts`, each `export const <name> = { ar: {...}, en: {...} }`) into `translations.ar` / `translations.en` keyed by namespace (e.g. `dashboard.*`, `admin.*`).
- `t(key, vars?)` does dot-path lookup with Arabic fallback and `{{var}}` interpolation.
- `src/lib/lenders.ts` (Jordanian bank/lender directory) is already bilingual — each institution has both `.ar` and `.en` fields; pick the right one based on `language`, don't add a separate dictionary for it.

**Why:** the app was originally Arabic-only with `dir="rtl"` hardcoded in `index.html` and `layout.tsx`; this pattern was chosen to add English without a new dependency and to let three subagents translate the large pages (admin.tsx, dashboard.tsx, wizard.tsx) in parallel without merge conflicts (each owns only its own dictionary file + its own page file).

**How to apply:** when adding new user-facing text to any DebtLens page, add both `ar` and `en` keys to that page's dictionary file and call `t('<namespace>.<key>')` — never hardcode Arabic strings or `dir="rtl"` again. Any locale-sensitive formatting (`toLocaleString`, `Intl.DateTimeFormat`) must branch on `language === 'ar' ? 'ar-JO' : 'en-US'`.
