export type BusinessNameMatchMethod =
  | "exact_normalized"
  | "legal_suffix_normalized"
  | "alias_token"
  | "acronym"
  | "token_overlap"
  | "typo"
  | "none";

export type BusinessNameMatchScore = {
  readonly matches: boolean;
  readonly score: number;
  readonly method: BusinessNameMatchMethod;
  readonly reason: string;
  readonly normalizedInput: string;
  readonly normalizedCandidate: string;
};

const LEGAL_SUFFIXES = [
  ["private", "limited"],
  ["pte", "ltd"],
  ["pte", "limited"],
  ["limited", "liability", "partnership"],
  ["llp"],
  ["lp"],
  ["ltd"],
  ["limited"],
  ["incorporated"],
  ["inc"],
  ["corporation"],
  ["corp"],
  ["company"],
  ["co"],
] as const;

const SIGNIFICANT_TOKEN_MIN_LENGTH = 2;
const MIN_MATCH_SCORE = 0.64;

export const normalizeBusinessNameForSearch = (value: string | undefined): string =>
  (value ?? "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();

const stripTrailingLegalSuffixes = (tokens: readonly string[]): readonly string[] => {
  let stripped = [...tokens];
  let changed = true;

  while (changed && stripped.length > 0) {
    changed = false;
    for (const suffix of LEGAL_SUFFIXES) {
      if (stripped.length < suffix.length) {
        continue;
      }
      const tail = stripped.slice(stripped.length - suffix.length);
      if (tail.every((token, index) => token === suffix[index])) {
        stripped = stripped.slice(0, stripped.length - suffix.length);
        changed = true;
        break;
      }
    }
  }

  return stripped.length === 0 ? tokens : stripped;
};

export const tokenizeBusinessName = (value: string | undefined): readonly string[] =>
  normalizeBusinessNameForSearch(value)
    .split(" ")
    .filter((token) => token.length >= SIGNIFICANT_TOKEN_MIN_LENGTH);

export const normalizeBusinessNameForMatch = (value: string | undefined): string =>
  stripTrailingLegalSuffixes(tokenizeBusinessName(value)).join(" ");

const buildAcronym = (tokens: readonly string[]): string =>
  tokens
    .filter((token) => token.length > 0)
    .map((token) => token[0])
    .join("");

const levenshteinDistance = (left: string, right: string): number => {
  if (left === right) {
    return 0;
  }
  if (left.length === 0) {
    return right.length;
  }
  if (right.length === 0) {
    return left.length;
  }

  const previous = Array.from({ length: right.length + 1 }, (_, index) => index);
  const current = Array.from({ length: right.length + 1 }, () => 0);

  for (let leftIndex = 1; leftIndex <= left.length; leftIndex += 1) {
    current[0] = leftIndex;
    for (let rightIndex = 1; rightIndex <= right.length; rightIndex += 1) {
      const substitutionCost = left[leftIndex - 1] === right[rightIndex - 1] ? 0 : 1;
      current[rightIndex] = Math.min(
        previous[rightIndex]! + 1,
        current[rightIndex - 1]! + 1,
        previous[rightIndex - 1]! + substitutionCost,
      );
    }
    for (let index = 0; index < previous.length; index += 1) {
      previous[index] = current[index]!;
    }
  }

  return previous[right.length]!;
};

const typoBudget = (length: number): number => {
  if (length < 4) return 0;
  if (length <= 6) return 1;
  if (length <= 12) return 2;
  return 3;
};

const tokenOverlapScore = (
  inputTokens: readonly string[],
  candidateTokens: readonly string[],
): number => {
  if (inputTokens.length === 0 || candidateTokens.length === 0) {
    return 0;
  }

  const inputSet = new Set(inputTokens);
  const candidateSet = new Set(candidateTokens);
  let overlap = 0;
  for (const token of inputSet) {
    if (candidateSet.has(token)) {
      overlap += 1;
    }
  }

  return overlap / Math.max(inputSet.size, candidateSet.size);
};

const clampScore = (score: number): number => Math.round(Math.min(Math.max(score, 0), 1) * 100) / 100;

export const scoreBusinessNameMatch = (
  input: string,
  candidate: string,
): BusinessNameMatchScore => {
  const normalizedInput = normalizeBusinessNameForSearch(input);
  const normalizedCandidateRaw = normalizeBusinessNameForSearch(candidate);
  const canonicalInput = normalizeBusinessNameForMatch(input);
  const canonicalCandidate = normalizeBusinessNameForMatch(candidate);
  const inputTokens = tokenizeBusinessName(canonicalInput);
  const candidateTokens = tokenizeBusinessName(canonicalCandidate);
  const inputAcronym = buildAcronym(inputTokens);
  const candidateAcronym = buildAcronym(candidateTokens);

  if (normalizedInput === "" || normalizedCandidateRaw === "") {
    return {
      matches: false,
      score: 0,
      method: "none",
      reason: "No comparable name text was available.",
      normalizedInput,
      normalizedCandidate: canonicalCandidate,
    };
  }

  if (normalizedInput === normalizedCandidateRaw) {
    return {
      matches: true,
      score: 1,
      method: "exact_normalized",
      reason: "Exact normalized name match.",
      normalizedInput,
      normalizedCandidate: normalizedCandidateRaw,
    };
  }

  if (canonicalInput !== "" && canonicalInput === canonicalCandidate) {
    return {
      matches: true,
      score: 0.96,
      method: "legal_suffix_normalized",
      reason: "Name matches after legal suffix normalization.",
      normalizedInput: canonicalInput,
      normalizedCandidate: canonicalCandidate,
    };
  }

  if (inputTokens.length === 1 && candidateTokens.includes(inputTokens[0]!)) {
    return {
      matches: true,
      score: 0.92,
      method: "alias_token",
      reason: "Input matches a significant token in the official name.",
      normalizedInput: canonicalInput,
      normalizedCandidate: canonicalCandidate,
    };
  }

  if (
    canonicalInput.length >= 2
    && (
      canonicalInput === candidateAcronym
      || (inputAcronym.length >= 2 && inputAcronym === candidateAcronym)
    )
  ) {
    return {
      matches: true,
      score: 0.9,
      method: "acronym",
      reason: "Input matches the candidate acronym.",
      normalizedInput: canonicalInput,
      normalizedCandidate: canonicalCandidate,
    };
  }

  const overlap = tokenOverlapScore(inputTokens, candidateTokens);
  if (inputTokens.length === candidateTokens.length && overlap >= 0.75) {
    return {
      matches: true,
      score: clampScore(0.72 + overlap * 0.14),
      method: "token_overlap",
      reason: "Most significant name tokens overlap.",
      normalizedInput: canonicalInput,
      normalizedCandidate: canonicalCandidate,
    };
  }

  const distance = levenshteinDistance(canonicalInput, canonicalCandidate);
  const maxLength = Math.max(canonicalInput.length, canonicalCandidate.length);
  const budget = typoBudget(maxLength);
  if (budget > 0 && distance <= budget) {
    return {
      matches: true,
      score: clampScore(0.7 - distance * 0.04),
      method: "typo",
      reason: `Name is within bounded typo distance ${distance}.`,
      normalizedInput: canonicalInput,
      normalizedCandidate: canonicalCandidate,
    };
  }

  return {
    matches: false,
    score: clampScore(Math.max(overlap * 0.6, 1 - distance / Math.max(maxLength, 1))),
    method: "none",
    reason: "Name did not meet bounded fuzzy-match thresholds.",
    normalizedInput: canonicalInput,
    normalizedCandidate: canonicalCandidate,
  };
};

export const isBusinessNameMatch = (input: string, candidate: string): boolean =>
  scoreBusinessNameMatch(input, candidate).matches;

export const rankBusinessNameCandidates = <TCandidate>(
  input: string,
  candidates: readonly TCandidate[],
  getNames: (candidate: TCandidate) => readonly string[],
): ReadonlyArray<TCandidate & { readonly matchScore: BusinessNameMatchScore }> =>
  candidates
    .flatMap((candidate) => {
      const best = getNames(candidate)
        .map((name) => scoreBusinessNameMatch(input, name))
        .sort((left, right) => right.score - left.score)[0];
      if (best === undefined || best.score < MIN_MATCH_SCORE) {
        return [];
      }
      return [{ ...candidate, matchScore: best }];
    })
    .sort((left, right) => right.matchScore.score - left.matchScore.score);
