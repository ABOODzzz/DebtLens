export interface DebtEntry {
  lenderName: string;
  startDate: string;
  remainingAmount: number;
}

export interface UserProfile {
  fullName?: string;
  nationalId?: string | null;
  hasBankAccount?: boolean;
  bankAccounts?: Array<{
    bankName: string;
    accountNumber: string;
    isSalaryAccount: boolean;
  }>;
  monthlySalary?: number | null;
  monthlyIncome?: number | null;
  employerName?: string | null;
  employmentType?: "permanent" | "temporary" | "unemployed" | null;
  hasOwnBusiness?: boolean | null;
  debts?: DebtEntry[];
  profileCompleted?: boolean;
  reviewStatus?: "pending" | "approved" | "rejected" | null;
}

/**
 * Heuristic amortization window (in months) used to translate a remaining
 * debt balance into an estimated monthly payment when no explicit
 * installment amount was collected from the user.
 */
const AMORTIZATION_MONTHS = 24;

export interface ComputedFinancials {
  monthlyIncome: number;
  debts: DebtEntry[];
  totalRemainingDebt: number;
  estimatedMonthlyDebtPayments: number;
  activeLoansCount: number;
  financingInstitutionsCount: number;
  debtToIncomeRatio: number;
  hasActiveLoans: boolean;
  hasMultipleFinancingInstitutions: boolean;
}

export function computeFinancials(profile: UserProfile): ComputedFinancials {
  const monthlyIncome = Number(
    profile.monthlySalary ?? profile.monthlyIncome ?? 0,
  );
  const debts = (profile.debts ?? []).filter(
    (d) => typeof d?.remainingAmount === "number" && d.remainingAmount > 0,
  );
  const totalRemainingDebt = debts.reduce(
    (sum, d) => sum + d.remainingAmount,
    0,
  );
  const estimatedMonthlyDebtPayments =
    totalRemainingDebt > 0 ? totalRemainingDebt / AMORTIZATION_MONTHS : 0;
  const activeLoansCount = debts.length;
  const financingInstitutionsCount = new Set(
    debts.map((d) => d.lenderName.trim().toLowerCase()),
  ).size;
  const debtToIncomeRatio =
    monthlyIncome > 0
      ? estimatedMonthlyDebtPayments / monthlyIncome
      : totalRemainingDebt > 0
        ? 1
        : 0;

  return {
    monthlyIncome,
    debts,
    totalRemainingDebt,
    estimatedMonthlyDebtPayments,
    activeLoansCount,
    financingInstitutionsCount,
    debtToIncomeRatio,
    hasActiveLoans: activeLoansCount > 0,
    hasMultipleFinancingInstitutions: financingInstitutionsCount >= 2,
  };
}
