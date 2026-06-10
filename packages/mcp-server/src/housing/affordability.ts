import { HOUSING_RULES } from "./rules.js";
import { computeGrantEligibility } from "./grants.js";
import type { HouseholdProfile, GrantEligibilityResult } from "./grants.js";
import { compareLoans } from "./loans.js";
import type { BankPackage, LoanCompareResult } from "./loans.js";

export type AffordabilityInput = {
  readonly profile: HouseholdProfile;
  readonly targetPriceSgd: number;
  readonly tenureYears: number;
  readonly cashOnHandSgd: number;
  readonly cpfOaBalanceSgd: number;
  readonly otherMonthlyDebtSgd?: number | undefined;
  readonly soraValue?: number | undefined;
  readonly bankPackages?: readonly BankPackage[] | undefined;
  readonly loanType?: "hdb" | "bank" | undefined;
};

export type DownpaymentBreakdown = {
  readonly totalSgd: number;
  readonly cashRequiredSgd: number;
  readonly cpfOrCashSgd: number;
  readonly cashAvailable: boolean;
  readonly cpfAvailable: boolean;
};

export type AffordabilityResult = {
  readonly verdict: "fits" | "tight" | "over_budget";
  readonly maxLoanByMsrSgd: number;
  readonly maxLoanByTdsrSgd: number;
  readonly maxLoanByLtvSgd: number;
  readonly recommendedLoanSgd: number;
  readonly downpayment: DownpaymentBreakdown;
  readonly grants: GrantEligibilityResult;
  readonly loans: LoanCompareResult;
  readonly netCashOutlaySgd: number;
  readonly bsdSgd: number;
  readonly monthlyInstalmentEstimateSgd: number;
  readonly monthlyIncomeSgd: number;
  readonly tdsrUtilization: number;
  readonly msrUtilization: number;
  readonly assumptions: readonly string[];
  readonly rulesVersion: string;
};

const monthlyPayment = (principal: number, annualRate: number, years: number): number => {
  if (principal <= 0 || years <= 0) return 0;
  const n = years * 12;
  const r = annualRate / 12;
  if (r === 0) return principal / n;
  return (principal * r) / (1 - Math.pow(1 + r, -n));
};

const presentValueOfAnnuity = (monthly: number, annualRate: number, years: number): number => {
  if (monthly <= 0 || years <= 0) return 0;
  const n = years * 12;
  const r = annualRate / 12;
  if (r === 0) return monthly * n;
  return monthly * (1 - Math.pow(1 + r, -n)) / r;
};

const computeBsd = (price: number): number => {
  let bsd = 0;
  let prev = 0;
  for (const tier of HOUSING_RULES.buyerStampDuty.tiers) {
    const cap = tier.uptoSgd ?? Infinity;
    const slice = Math.max(0, Math.min(price, cap) - prev);
    bsd += slice * tier.rate;
    prev = cap;
    if (cap >= price) break;
  }
  return Math.round(bsd * 100) / 100;
};

const round2 = (n: number): number => Math.round(n * 100) / 100;

export const computeAffordability = (input: AffordabilityInput): AffordabilityResult => {
  const { profile, targetPriceSgd, tenureYears, cashOnHandSgd, cpfOaBalanceSgd } = input;
  const otherDebt = input.otherMonthlyDebtSgd ?? 0;
  const monthlyIncome = profile.applicants.reduce((acc, a) => acc + a.monthlyIncomeSgd, 0);

  const stressRate = HOUSING_RULES.bankLoanTemplate.stressTestRate;
  const msrCap = monthlyIncome * HOUSING_RULES.servicingRatios.msr;
  const tdsrCap = monthlyIncome * HOUSING_RULES.servicingRatios.tdsr - otherDebt;

  const maxLoanByMsr = presentValueOfAnnuity(msrCap, stressRate, tenureYears);
  const maxLoanByTdsr = presentValueOfAnnuity(Math.max(0, tdsrCap), stressRate, tenureYears);

  const useHdb = input.loanType !== "bank";
  const ltv = useHdb ? HOUSING_RULES.hdbLoan.ltvRatio : HOUSING_RULES.bankLoanTemplate.ltvRatio;
  const maxLoanByLtv = targetPriceSgd * ltv;

  const recommendedLoan = Math.min(maxLoanByMsr, maxLoanByTdsr, maxLoanByLtv);

  const minDownpayment = targetPriceSgd - recommendedLoan;
  const minCashPercent = useHdb ? HOUSING_RULES.hdbLoan.minDownpaymentCash : HOUSING_RULES.bankLoanTemplate.minDownpaymentCashPercent;
  const cashRequired = targetPriceSgd * minCashPercent;
  const cpfOrCash = Math.max(0, minDownpayment - cashRequired);

  const grants = computeGrantEligibility(profile);
  const loans = compareLoans({
    priceSgd: targetPriceSgd,
    downpaymentSgd: minDownpayment,
    tenureYears,
    ...(input.soraValue === undefined ? {} : { soraValue: input.soraValue }),
    ...(input.bankPackages === undefined ? {} : { bankPackages: input.bankPackages }),
    includeHdbLoan: useHdb,
  });

  const primaryRate = useHdb ? HOUSING_RULES.hdbLoan.interestRate : (input.soraValue ?? HOUSING_RULES.bankLoanTemplate.stressTestRate);
  const monthlyInstalment = monthlyPayment(recommendedLoan, primaryRate, tenureYears);

  const bsd = computeBsd(targetPriceSgd);
  const netCash = Math.max(0, cashRequired + bsd - grants.totalSgd);

  const tdsrUtil = monthlyIncome === 0 ? 0 : (monthlyInstalment + otherDebt) / monthlyIncome;
  const msrUtil = monthlyIncome === 0 ? 0 : monthlyInstalment / monthlyIncome;

  let verdict: "fits" | "tight" | "over_budget" = "fits";
  if (cashOnHandSgd < cashRequired) verdict = "over_budget";
  else if (cpfOaBalanceSgd + cashOnHandSgd - cashRequired < cpfOrCash) verdict = "over_budget";
  else if (msrUtil > HOUSING_RULES.servicingRatios.msr || tdsrUtil > HOUSING_RULES.servicingRatios.tdsr) verdict = "over_budget";
  else if (msrUtil > HOUSING_RULES.servicingRatios.msr * 0.9 || tdsrUtil > HOUSING_RULES.servicingRatios.tdsr * 0.9) verdict = "tight";

  return {
    verdict,
    maxLoanByMsrSgd: round2(maxLoanByMsr),
    maxLoanByTdsrSgd: round2(maxLoanByTdsr),
    maxLoanByLtvSgd: round2(maxLoanByLtv),
    recommendedLoanSgd: round2(recommendedLoan),
    downpayment: {
      totalSgd: round2(minDownpayment),
      cashRequiredSgd: round2(cashRequired),
      cpfOrCashSgd: round2(cpfOrCash),
      cashAvailable: cashOnHandSgd >= cashRequired,
      cpfAvailable: cpfOaBalanceSgd >= cpfOrCash,
    },
    grants,
    loans,
    netCashOutlaySgd: round2(netCash),
    bsdSgd: round2(bsd),
    monthlyInstalmentEstimateSgd: round2(monthlyInstalment),
    monthlyIncomeSgd: monthlyIncome,
    tdsrUtilization: round2(tdsrUtil * 10000) / 10000,
    msrUtilization: round2(msrUtil * 10000) / 10000,
    assumptions: [
      "Max-loan checks use the MAS 4% medium-term stress rate as required for affordability assessment.",
      "Monthly instalment uses the contractual rate (HDB or supplied bank rate), not the stress rate.",
      "Cash/CPF split uses the loan-type minimum downpayment rule from the rules config.",
      "BSD is residential tier-based and does not apply ABSD (foreigners/2nd-home/PR/entity).",
      "Grants are netted against cash outlay only; CPF disbursement timing differs.",
      "Other monthly debts are subtracted from TDSR before sizing the loan.",
    ],
    rulesVersion: HOUSING_RULES.version,
  };
};
