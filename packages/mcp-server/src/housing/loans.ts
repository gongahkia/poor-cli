import { HOUSING_RULES } from "./rules.js";

export type BankPackage = {
  readonly bank: string;
  readonly packageName: string;
  readonly rateBasis: "sora_1m" | "sora_3m" | "fixed" | "board_rate";
  readonly spreadBps?: number | undefined;
  readonly fixedRate?: number | undefined;
  readonly lockInYears?: number | undefined;
  readonly thereafterSpreadBps?: number | undefined;
  readonly notes?: string | undefined;
};

export type LoanCompareInput = {
  readonly priceSgd: number;
  readonly downpaymentSgd: number;
  readonly tenureYears: number;
  readonly soraValue?: number | undefined;
  readonly soraTenor?: "1m" | "3m" | undefined;
  readonly bankPackages?: readonly BankPackage[] | undefined;
  readonly includeHdbLoan?: boolean | undefined;
};

export type LoanQuote = {
  readonly source: string;
  readonly product: string;
  readonly principalSgd: number;
  readonly tenureYears: number;
  readonly effectiveYear1Rate: number;
  readonly thereafterRate: number;
  readonly monthlyInstalmentYear1Sgd: number;
  readonly monthlyInstalmentThereafterSgd: number;
  readonly totalInterestEstimateSgd: number;
  readonly stressTestPassed: boolean;
  readonly notes: readonly string[];
};

export type LoanCompareResult = {
  readonly principalSgd: number;
  readonly tenureYears: number;
  readonly stressRate: number;
  readonly quotes: readonly LoanQuote[];
  readonly bestByYear1: string | null;
  readonly bestByLifetime: string | null;
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

const totalInterest = (principal: number, annualRate: number, years: number): number => {
  return Math.max(0, monthlyPayment(principal, annualRate, years) * years * 12 - principal);
};

const round2 = (n: number): number => Math.round(n * 100) / 100;

const resolveBankRate = (pkg: BankPackage, soraValue: number): { y1: number; thereafter: number } => {
  const bps = (b?: number): number => (b ?? 0) / 10000;
  if (pkg.rateBasis === "fixed") {
    const fixed = pkg.fixedRate ?? 0;
    return { y1: fixed, thereafter: soraValue + bps(pkg.thereafterSpreadBps ?? pkg.spreadBps) };
  }
  if (pkg.rateBasis === "board_rate") {
    const fixed = pkg.fixedRate ?? 0;
    return { y1: fixed, thereafter: fixed };
  }
  const y1 = soraValue + bps(pkg.spreadBps);
  const thereafter = soraValue + bps(pkg.thereafterSpreadBps ?? pkg.spreadBps);
  return { y1, thereafter };
};

export const compareLoans = (input: LoanCompareInput): LoanCompareResult => {
  const principal = Math.max(0, input.priceSgd - input.downpaymentSgd);
  const tenure = input.tenureYears;
  const stressRate = HOUSING_RULES.bankLoanTemplate.stressTestRate;
  const quotes: LoanQuote[] = [];

  if (input.includeHdbLoan !== false) {
    const r = HOUSING_RULES.hdbLoan.interestRate;
    const tenureCap = Math.min(tenure, HOUSING_RULES.hdbLoan.maxTenureYears);
    const y1 = monthlyPayment(principal, r, tenureCap);
    quotes.push({
      source: "HDB",
      product: HOUSING_RULES.hdbLoan.name,
      principalSgd: round2(principal),
      tenureYears: tenureCap,
      effectiveYear1Rate: r,
      thereafterRate: r,
      monthlyInstalmentYear1Sgd: round2(y1),
      monthlyInstalmentThereafterSgd: round2(y1),
      totalInterestEstimateSgd: round2(totalInterest(principal, r, tenureCap)),
      stressTestPassed: monthlyPayment(principal, stressRate, tenureCap) > 0,
      notes: [
        `Pegged at CPF-OA ${HOUSING_RULES.hdbLoan.cpfOaRate * 100}% + ${HOUSING_RULES.hdbLoan.spread * 100}% spread.`,
        `Max tenure ${HOUSING_RULES.hdbLoan.maxTenureYears}y; capped to input tenure.`,
        "Eligibility requires meeting HDB income ceilings and ownership history.",
      ],
    });
  }

  const sora = input.soraValue;
  const packages = input.bankPackages ?? [];

  for (const pkg of packages) {
    if (pkg.rateBasis !== "fixed" && pkg.rateBasis !== "board_rate" && sora === undefined) {
      quotes.push({
        source: pkg.bank,
        product: pkg.packageName,
        principalSgd: round2(principal),
        tenureYears: tenure,
        effectiveYear1Rate: 0,
        thereafterRate: 0,
        monthlyInstalmentYear1Sgd: 0,
        monthlyInstalmentThereafterSgd: 0,
        totalInterestEstimateSgd: 0,
        stressTestPassed: false,
        notes: [`SORA value missing; cannot price ${pkg.rateBasis} package. Pass soraValue from sg_mas_interest_rates.`],
      });
      continue;
    }
    const { y1, thereafter } = resolveBankRate(pkg, sora ?? 0);
    const lockIn = pkg.lockInYears ?? 0;
    const lockInPayment = monthlyPayment(principal, y1, tenure);
    const thereafterPayment = monthlyPayment(principal, thereafter, tenure);
    const blendedInterest = (lockIn > 0 && lockIn < tenure)
      ? totalInterest(principal, y1, tenure) * (lockIn / tenure) + totalInterest(principal, thereafter, tenure) * ((tenure - lockIn) / tenure)
      : totalInterest(principal, lockIn === 0 ? thereafter : y1, tenure);
    quotes.push({
      source: pkg.bank,
      product: pkg.packageName,
      principalSgd: round2(principal),
      tenureYears: tenure,
      effectiveYear1Rate: round2(y1 * 10000) / 10000,
      thereafterRate: round2(thereafter * 10000) / 10000,
      monthlyInstalmentYear1Sgd: round2(lockInPayment),
      monthlyInstalmentThereafterSgd: round2(thereafterPayment),
      totalInterestEstimateSgd: round2(blendedInterest),
      stressTestPassed: monthlyPayment(principal, stressRate, tenure) > 0,
      notes: [
        pkg.rateBasis === "fixed" ? `Fixed rate ${pkg.fixedRate}` : `${pkg.rateBasis} + ${pkg.spreadBps ?? 0}bps spread`,
        lockIn > 0 ? `${lockIn}y lock-in.` : "No lock-in.",
        ...(pkg.notes === undefined ? [] : [pkg.notes]),
      ],
    });
  }

  const valid = quotes.filter((q) => q.monthlyInstalmentYear1Sgd > 0);
  const bestY1Quote = valid.length === 0 ? null : valid.reduce((min, q) => q.monthlyInstalmentYear1Sgd < min.monthlyInstalmentYear1Sgd ? q : min);
  const bestLifetimeQuote = valid.length === 0 ? null : valid.reduce((min, q) => q.totalInterestEstimateSgd < min.totalInterestEstimateSgd ? q : min);
  const bestByYear1 = bestY1Quote === null ? null : `${bestY1Quote.source}:${bestY1Quote.product}`;
  const bestByLifetime = bestLifetimeQuote === null ? null : `${bestLifetimeQuote.source}:${bestLifetimeQuote.product}`;

  return {
    principalSgd: round2(principal),
    tenureYears: tenure,
    stressRate,
    quotes,
    bestByYear1,
    bestByLifetime,
    assumptions: [
      "Bank packages are caller-supplied; HDB loan rate uses CPF-OA + 0.1% from rules config.",
      "Lock-in blended interest is an approximation; banks compute exact reducing-balance schedules.",
      "MAS stress test floor (4%) is reported but instalments use the contractual rate.",
      "Tenure is capped at HDB max for the HDB loan quote.",
    ],
    rulesVersion: HOUSING_RULES.version,
  };
};
