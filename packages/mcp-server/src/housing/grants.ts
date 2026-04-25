import { HOUSING_RULES } from "./rules.js";

export type Citizenship = "citizen" | "pr" | "foreigner";
export type MaritalStatus = "single" | "married" | "joint_singles" | "fiance_fiancee";
export type FlatPurchaseMode = "bto" | "resale";
export type FlatSizeBand = "2_room" | "3_room" | "4_room" | "5_room" | "executive";

export type Applicant = {
  readonly age: number;
  readonly citizenship: Citizenship;
  readonly monthlyIncomeSgd: number;
  readonly employmentMonths?: number | undefined;
  readonly firstTimer?: boolean | undefined;
};

export type HouseholdProfile = {
  readonly applicants: readonly Applicant[];
  readonly maritalStatus: MaritalStatus;
  readonly flatMode: FlatPurchaseMode;
  readonly flatSize: FlatSizeBand;
  readonly proximityToParents?: "live_with" | "near" | "neither" | undefined;
  readonly upgradingFromTwoRoomBtoNonMature?: boolean | undefined;
};

export type GrantLine = {
  readonly id: string;
  readonly name: string;
  readonly amountSgd: number;
  readonly basis: string;
  readonly source: string;
};

export type GrantBlocker = {
  readonly grantId: string;
  readonly code: string;
  readonly message: string;
};

export type GrantEligibilityResult = {
  readonly eligible: readonly GrantLine[];
  readonly ineligible: readonly GrantBlocker[];
  readonly totalSgd: number;
  readonly householdIncomeSgd: number;
  readonly assumptions: readonly string[];
  readonly rulesVersion: string;
  readonly rulesLastVerified: string;
};

const sumIncome = (applicants: readonly Applicant[]): number => {
  return applicants.reduce((acc, a) => acc + (a.monthlyIncomeSgd || 0), 0);
};

const isFamilyHousehold = (m: MaritalStatus): boolean => {
  return m === "married" || m === "fiance_fiancee";
};

const isSinglesHousehold = (m: MaritalStatus): boolean => {
  return m === "single" || m === "joint_singles";
};

const allFirstTimer = (a: readonly Applicant[]): boolean => {
  return a.every((x) => x.firstTimer !== false);
};

const flatSizeBucket = (s: FlatSizeBand): "2_to_4" | "5_plus" => {
  return s === "5_room" || s === "executive" ? "5_plus" : "2_to_4";
};

const minCitizenship = (a: readonly Applicant[]): Citizenship => {
  if (a.some((x) => x.citizenship === "foreigner")) return "foreigner";
  if (a.some((x) => x.citizenship === "pr")) return "pr";
  return "citizen";
};

const computeEhg = (profile: HouseholdProfile, blockers: GrantBlocker[]): GrantLine | null => {
  const r = HOUSING_RULES.ehg;
  const income = sumIncome(profile.applicants);
  const family = isFamilyHousehold(profile.maritalStatus);
  const singles = isSinglesHousehold(profile.maritalStatus);
  const ceiling = singles && profile.maritalStatus === "single"
    ? r.singlesIncomeCeilingSgd
    : r.incomeCeilingSgd;

  if (minCitizenship(profile.applicants) === "foreigner") {
    blockers.push({ grantId: "ehg", code: "NO_CITIZEN", message: "EHG requires at least one Singapore Citizen applicant." });
    return null;
  }
  if (!allFirstTimer(profile.applicants)) {
    blockers.push({ grantId: "ehg", code: "NOT_FIRST_TIMER", message: "EHG requires all applicants to be first-timers." });
    return null;
  }
  if (income > ceiling) {
    blockers.push({ grantId: "ehg", code: "INCOME_OVER_CEILING", message: `Household income ${income} exceeds EHG ceiling ${ceiling}.` });
    return null;
  }
  const empMonths = Math.min(...profile.applicants.map((a) => a.employmentMonths ?? r.minEmploymentMonths));
  if (empMonths < r.minEmploymentMonths) {
    blockers.push({ grantId: "ehg", code: "EMPLOYMENT_INSUFFICIENT", message: `EHG requires ${r.minEmploymentMonths} months continuous employment.` });
    return null;
  }
  const tier = r.tiers.find((t) => income <= t.incomeMaxSgd);
  if (tier === undefined) return null;
  const amount = profile.maritalStatus === "single" ? tier.amountSgd / 2 : tier.amountSgd;
  return {
    id: "ehg",
    name: r.name,
    amountSgd: amount,
    basis: family ? `Family tier: income <= ${tier.incomeMaxSgd}` : `Singles half-tier: income <= ${tier.incomeMaxSgd}`,
    source: HOUSING_RULES.sources["ehg"] ?? "",
  };
};

const computeFamilyGrant = (profile: HouseholdProfile, blockers: GrantBlocker[]): GrantLine | null => {
  const r = HOUSING_RULES.familyGrant;
  if (profile.flatMode !== "resale") return null;
  if (!isFamilyHousehold(profile.maritalStatus)) {
    blockers.push({ grantId: "family_grant", code: "WRONG_HOUSEHOLD", message: "Family Grant is for couples/fiancé(e)s." });
    return null;
  }
  const cit = minCitizenship(profile.applicants);
  if (cit === "foreigner") {
    blockers.push({ grantId: "family_grant", code: "NO_CITIZEN", message: "Family Grant requires citizen applicants." });
    return null;
  }
  if (!allFirstTimer(profile.applicants)) {
    blockers.push({ grantId: "family_grant", code: "NOT_FIRST_TIMER", message: "Family Grant requires first-timer status." });
    return null;
  }
  const income = sumIncome(profile.applicants);
  if (income > r.incomeCeilingSgd) {
    blockers.push({ grantId: "family_grant", code: "INCOME_OVER_CEILING", message: `Income ${income} exceeds Family Grant ceiling ${r.incomeCeilingSgd}.` });
    return null;
  }
  const sizeBucket = flatSizeBucket(profile.flatSize);
  const allCitizen = profile.applicants.every((a) => a.citizenship === "citizen");
  const key = allCitizen
    ? (sizeBucket === "5_plus" ? "citizenCitizen5RoomPlus" : "citizenCitizen2to4Room")
    : (sizeBucket === "5_plus" ? "citizenPr5RoomPlus" : "citizenPr2to4Room");
  const amount = r.amounts[key];
  if (amount === undefined) return null;
  return {
    id: "family_grant",
    name: r.name,
    amountSgd: amount,
    basis: `${allCitizen ? "SC/SC" : "SC/PR"} household, ${sizeBucket === "5_plus" ? "5-room+" : "2-4 room"}`,
    source: HOUSING_RULES.sources["familyGrant"] ?? "",
  };
};

const computeSinglesGrant = (profile: HouseholdProfile, blockers: GrantBlocker[]): GrantLine | null => {
  const r = HOUSING_RULES.singlesGrant;
  if (profile.flatMode !== "resale") return null;
  if (!isSinglesHousehold(profile.maritalStatus)) return null;
  const minAge = Math.min(...profile.applicants.map((a) => a.age));
  if (minAge < r.minAge) {
    blockers.push({ grantId: "singles_grant", code: "AGE_BELOW_35", message: `Singles Grant requires age >= ${r.minAge}.` });
    return null;
  }
  if (profile.applicants.some((a) => a.citizenship !== "citizen")) {
    blockers.push({ grantId: "singles_grant", code: "NOT_CITIZEN", message: "Singles Grant requires Singapore citizenship." });
    return null;
  }
  if (!allFirstTimer(profile.applicants)) {
    blockers.push({ grantId: "singles_grant", code: "NOT_FIRST_TIMER", message: "Singles Grant requires first-timer status." });
    return null;
  }
  const income = sumIncome(profile.applicants);
  if (income > r.incomeCeilingSgd) {
    blockers.push({ grantId: "singles_grant", code: "INCOME_OVER_CEILING", message: `Income ${income} exceeds Singles Grant ceiling ${r.incomeCeilingSgd}.` });
    return null;
  }
  const sizeBucket = flatSizeBucket(profile.flatSize);
  const isJoint = profile.maritalStatus === "joint_singles";
  const key = isJoint
    ? (sizeBucket === "5_plus" ? "jointSingles5RoomPlus" : "jointSingles2to4Room")
    : (sizeBucket === "5_plus" ? "citizen5RoomPlus" : "citizen2to4Room");
  const amount = r.amounts[key];
  if (amount === undefined) return null;
  return {
    id: "singles_grant",
    name: r.name,
    amountSgd: amount,
    basis: `${isJoint ? "Joint Singles" : "Single"}, ${sizeBucket === "5_plus" ? "5-room+" : "2-4 room"}`,
    source: HOUSING_RULES.sources["singlesGrant"] ?? "",
  };
};

const computeProximityGrant = (profile: HouseholdProfile): GrantLine | null => {
  const r = HOUSING_RULES.proximityGrant;
  if (profile.flatMode !== "resale") return null;
  const proximity = profile.proximityToParents;
  if (proximity === undefined || proximity === "neither") return null;
  const family = isFamilyHousehold(profile.maritalStatus);
  const key = family
    ? (proximity === "live_with" ? "familyLiveWithParents" : "familyNearParents")
    : (proximity === "live_with" ? "singleLiveWithParents" : "singleNearParents");
  const amount = r.amounts[key];
  if (amount === undefined) return null;
  return {
    id: "proximity_grant",
    name: r.name,
    amountSgd: amount,
    basis: `${family ? "Family" : "Singles"}, ${proximity === "live_with" ? "live with" : `within ${r.proximityKm}km of`} parents`,
    source: HOUSING_RULES.sources["proximityGrant"] ?? "",
  };
};

const computeStepUpGrant = (profile: HouseholdProfile, blockers: GrantBlocker[]): GrantLine | null => {
  const r = HOUSING_RULES.stepUpGrant;
  if (profile.upgradingFromTwoRoomBtoNonMature !== true) return null;
  if (allFirstTimer(profile.applicants)) {
    blockers.push({ grantId: "step_up", code: "FIRST_TIMER", message: "Step-Up Grant is for second-timer families only." });
    return null;
  }
  const income = sumIncome(profile.applicants);
  if (income > r.incomeCeilingSgd) {
    blockers.push({ grantId: "step_up", code: "INCOME_OVER_CEILING", message: `Income exceeds Step-Up ceiling ${r.incomeCeilingSgd}.` });
    return null;
  }
  return {
    id: "step_up",
    name: r.name,
    amountSgd: r.amountSgd,
    basis: "Second-timer family upgrading 2-room to 3-room non-mature",
    source: HOUSING_RULES.sources["stepUpGrant"] ?? "",
  };
};

export const computeGrantEligibility = (profile: HouseholdProfile): GrantEligibilityResult => {
  const blockers: GrantBlocker[] = [];
  const lines: GrantLine[] = [];

  const ehg = computeEhg(profile, blockers);
  if (ehg !== null) lines.push(ehg);

  const family = computeFamilyGrant(profile, blockers);
  if (family !== null) lines.push(family);

  const singles = computeSinglesGrant(profile, blockers);
  if (singles !== null) lines.push(singles);

  const proximity = computeProximityGrant(profile);
  if (proximity !== null) lines.push(proximity);

  const stepUp = computeStepUpGrant(profile, blockers);
  if (stepUp !== null) lines.push(stepUp);

  const total = lines.reduce((acc, l) => acc + l.amountSgd, 0);
  const assumptions: string[] = [
    "All applicants must meet HDB ethnic-integration policy and citizenship rules independently.",
    "Singles grants require Singapore Citizenship at age >= 35 (Single) or both citizens >= 35 (Joint Singles).",
    "EHG requires 12 months continuous employment at time of application.",
    "Proximity Housing Grant requires the parent address to be in Singapore.",
    "BSD/ABSD and stamp duty rebates are not netted in the grant total.",
    "Grant rules and amounts are sourced from the embedded rules file; verify against HDB site for live application.",
  ];

  return {
    eligible: lines,
    ineligible: blockers,
    totalSgd: total,
    householdIncomeSgd: sumIncome(profile.applicants),
    assumptions,
    rulesVersion: HOUSING_RULES.version,
    rulesLastVerified: HOUSING_RULES.lastVerified,
  };
};
