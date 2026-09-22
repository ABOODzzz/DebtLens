/**
 * Bilingual (EN / AR) directory of Jordanian financial institutions.
 *
 * - `banks`: licensed commercial/Islamic banks — used for the bank-account
 *   dropdown in the profile wizard.
 * - `leasingFinanceCompanies`, `microfinanceInstitutions`, `paymentApps`:
 *   non-bank lenders/payment providers — combined with `banks` via
 *   `allLenders` for the debt checklist's lender dropdown.
 */

export interface Institution {
  en: string;
  ar: string;
}

export const banks: Institution[] = [
  { en: "Arab Bank", ar: "البنك العربي" },
  { en: "Bank of Jordan", ar: "بنك الأردن" },
  { en: "Jordan Ahli Bank", ar: "البنك الأهلي الأردني" },
  { en: "Cairo Amman Bank", ar: "بنك القاهرة عمان" },
  { en: "Jordan Kuwait Bank", ar: "بنك الأردن الكويت" },
  { en: "Jordan Commercial Bank", ar: "البنك التجاري الأردني" },
  { en: "Arab Jordan Investment Bank", ar: "بنك الاستثمار العربي الأردني" },
  { en: "Housing Bank for Trade and Finance", ar: "بنك الإسكان" },
  { en: "Bank al Etihad", ar: "بنك الاتحاد" },
  { en: "Capital Bank of Jordan", ar: "كابيتال بنك" },
  { en: "Investbank", ar: "إنفستبنك" },
  { en: "Jordan Islamic Bank", ar: "البنك الإسلامي الأردني" },
  { en: "Islamic International Arab Bank", ar: "البنك العربي الإسلامي الدولي" },
  { en: "Safwa Islamic Bank", ar: "مصرف صفوة الإسلامي" },
  { en: "Al Rajhi Bank Jordan", ar: "مصرف الراجحي الأردن" },
  { en: "BLOM Bank Jordan", ar: "بنك بلوم" },
  { en: "Bank ABC Jordan", ar: "بنك ABC" },
  { en: "Egyptian Arab Land Bank", ar: "البنك العقاري المصري العربي" },
  { en: "Rafidain Bank", ar: "مصرف الرافدين" },
  { en: "Citibank", ar: "سيتي بنك" },
];

export const leasingFinanceCompanies: Institution[] = [
  { en: "Sanadcom SME Finance", ar: "شركة سندكم لتمويل المشاريع الصغيرة والمتوسطة" },
  { en: "Al Baraka Islamic Finance", ar: "شركة البركة للتمويل الإسلامي" },
  { en: "Valu Specialized Finance", ar: "شركة فاليو للتمويل المتخصص" },
  { en: "Al Samaha Islamic Finance", ar: "شركة السماحة للتمويل الإسلامي" },
  { en: "Ejara Leasing", ar: "شركة إجارة للتأجير التمويلي" },
  { en: "Arab National Leasing Company", ar: "الشركة العربية الوطنية للتأجير التمويلي" },
  { en: "Jordan Money Leasing Company", ar: "شركة المال الأردني للتأجير التمويلي" },
  { en: "Al Etihad Leasing Company", ar: "شركة الاتحاد للتأجير التمويلي" },
  { en: "Al Ahli Leasing Company", ar: "شركة الأهلي للتأجير التمويلي" },
  { en: "Jordan Facilities Specialized Finance", ar: "شركة التسهيلات الأردنية للتمويل المتخصص" },
  { en: "Al Kawthar Leasing Company", ar: "شركة الكوثر للتأجير التمويلي" },
  { en: "Tamalak Leasing Company", ar: "شركة تملك للتأجير التمويلي" },
  { en: "Tamkeen Leasing Company", ar: "شركة تمكين للتأجير التمويلي" },
];

export const microfinanceInstitutions: Institution[] = [
  { en: "Ahli Microfinance", ar: "الأهلي للتمويل الأصغر" },
  { en: "Vitas Jordan", ar: "الشركاء للتمويل الأصغر" },
  { en: "Tamweelcom", ar: "الشركة الأردنية للتمويل الأصغر" },
  { en: "National Microfinance Bank", ar: "الوطني للتمويل الأصغر" },
  { en: "Al Ameen Microfinance", ar: "الأمين للتمويل الأصغر" },
  { en: "Microfund for Women", ar: "صندوق المرأة للتمويل الأصغر" },
  { en: "FINCA Jordan", ar: "فينكا الأردن" },
  { en: "Islamic Model Microfinance", ar: "النموذجية الإسلامية للتمويل الأصغر" },
];

export const paymentApps: Institution[] = [
  { en: "YenCash", ar: "ين كاش" },
  { en: "Orange Money", ar: "أورنج موني" },
  { en: "Dinarak", ar: "دينارك" },
  { en: "UWallet", ar: "يو والت" },
  { en: "Mad Pay", ar: "مدفوعاتكم" },
  { en: "Gate2Pay", ar: "إيلاف الأردنية" },
  { en: "MEPS", ar: "الشرق الأوسط لخدمات الدفع" },
  { en: "Alawneh Pay", ar: "العلاونة لخدمات الدفع" },
  { en: "American Express", ar: "أمريكان إكسبرس" },
  { en: "National Express", ar: "ناشونال إكسبرس" },
];

/** Full combined directory, used for the debt checklist's lender dropdown. */
export const allLenders: Institution[] = [
  ...banks,
  ...leasingFinanceCompanies,
  ...microfinanceInstitutions,
  ...paymentApps,
];
