import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { translations, type Language } from './translations';

const STORAGE_KEY = 'debtlens-language';

function detectInitialLanguage(): Language {
  if (typeof window === 'undefined') return 'ar';
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === 'ar' || stored === 'en') return stored;
  return 'ar';
}

function getByPath(obj: any, path: string): unknown {
  return path.split('.').reduce((acc, key) => (acc == null ? undefined : acc[key]), obj);
}

interface LanguageContextValue {
  language: Language;
  dir: 'rtl' | 'ltr';
  setLanguage: (language: Language) => void;
  toggleLanguage: () => void;
  /** Looks up `key` (dot path) in the active language dictionary; falls back to Arabic, then the key itself. Supports `{{var}}` interpolation via `vars`. */
  t: (key: string, vars?: Record<string, string | number>) => string;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(detectInitialLanguage);
  const dir: 'rtl' | 'ltr' = language === 'ar' ? 'rtl' : 'ltr';

  useEffect(() => {
    document.documentElement.lang = language;
    document.documentElement.dir = dir;
    window.localStorage.setItem(STORAGE_KEY, language);
  }, [language, dir]);

  const setLanguage = (next: Language) => setLanguageState(next);
  const toggleLanguage = () => setLanguageState((prev) => (prev === 'ar' ? 'en' : 'ar'));

  const t = useMemo(() => {
    return (key: string, vars?: Record<string, string | number>) => {
      const value = getByPath(translations[language], key) ?? getByPath(translations.ar, key);
      let result = typeof value === 'string' ? value : key;
      if (vars) {
        for (const [varKey, varValue] of Object.entries(vars)) {
          result = result.replaceAll(`{{${varKey}}}`, String(varValue));
        }
      }
      return result;
    };
  }, [language]);

  const contextValue = useMemo(
    () => ({ language, dir, setLanguage, toggleLanguage, t }),
    [language, dir, t],
  );

  return <LanguageContext.Provider value={contextValue}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error('useLanguage must be used within a LanguageProvider');
  return ctx;
}
