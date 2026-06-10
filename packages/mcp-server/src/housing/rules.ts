import rulesJson from "./rules-2026.json" with { type: "json" };

export type EhgTier = { readonly incomeMaxSgd: number; readonly amountSgd: number };

export type HousingRules = {
  readonly version: string;
  readonly effectiveFrom: string;
  readonly lastVerified: string;
  readonly sources: Readonly<Record<string, string>>;
  readonly verificationNote: string;
  readonly ehg: {
    readonly name: string;
    readonly appliesTo: readonly string[];
    readonly incomeCeilingSgd: number;
    readonly minEmploymentMonths: number;
    readonly tiers: readonly EhgTier[];
    readonly singlesHalfRule: string;
    readonly singlesIncomeCeilingSgd: number;
  };
  readonly familyGrant: {
    readonly name: string;
    readonly appliesTo: readonly string[];
    readonly incomeCeilingSgd: number;
    readonly amounts: Readonly<Record<string, number>>;
  };
  readonly singlesGrant: {
    readonly name: string;
    readonly appliesTo: readonly string[];
    readonly minAge: number;
    readonly incomeCeilingSgd: number;
    readonly amounts: Readonly<Record<string, number>>;
  };
  readonly proximityGrant: {
    readonly name: string;
    readonly appliesTo: readonly string[];
    readonly amounts: Readonly<Record<string, number>>;
    readonly proximityKm: number;
  };
  readonly stepUpGrant: {
    readonly name: string;
    readonly appliesTo: readonly string[];
    readonly scope: string;
    readonly incomeCeilingSgd: number;
    readonly amountSgd: number;
  };
  readonly hdbLoan: {
    readonly name: string;
    readonly rateBasis: string;
    readonly cpfOaRate: number;
    readonly spread: number;
    readonly interestRate: number;
    readonly ltvRatio: number;
    readonly minDownpaymentCash: number;
    readonly minDownpaymentCpfOrCash: number;
    readonly incomeCeilingFamilySgd: number;
    readonly incomeCeilingExtendedFamilySgd: number;
    readonly incomeCeilingSinglesSgd: number;
    readonly maxTenureYears: number;
    readonly maxAge: number;
  };
  readonly bankLoanTemplate: {
    readonly name: string;
    readonly rateBasis: string;
    readonly ltvRatio: number;
    readonly minDownpaymentCashPercent: number;
    readonly minDownpaymentCpfOrCashPercent: number;
    readonly maxTenureYears: number;
    readonly maxAge: number;
    readonly stressTestRate: number;
    readonly note: string;
  };
  readonly servicingRatios: {
    readonly msr: number;
    readonly tdsr: number;
    readonly msrAppliesTo: string;
  };
  readonly buyerStampDuty: {
    readonly tiers: readonly { readonly uptoSgd: number | null; readonly rate: number }[];
    readonly note: string;
  };
};

export const HOUSING_RULES = rulesJson as unknown as HousingRules;

export const rulesProvenance = (): {
  readonly version: string;
  readonly lastVerified: string;
  readonly effectiveFrom: string;
  readonly note: string;
} => ({
  version: HOUSING_RULES.version,
  lastVerified: HOUSING_RULES.lastVerified,
  effectiveFrom: HOUSING_RULES.effectiveFrom,
  note: HOUSING_RULES.verificationNote,
});
