import { describe, expect, it } from "vitest";
import {
  EcdaChildcareCentresSchema,
  PaCommunityOutletsSchema,
  PaResidentNetworkCentresSchema,
  SportSgFacilitiesSchema,
} from "../schemas/index.js";

describe("civic directory schemas", () => {
  it("accepts bounded PA community outlet filters", () => {
    expect(
      PaCommunityOutletsSchema.safeParse({
        type: "community_club",
        postalCode: "560123",
        lat: 1.33,
        lng: 103.85,
        radiusKm: 3,
        limit: 10,
        format: "geojson",
      }).success,
    ).toBe(true);
  });

  it("requires lat and lng together for civic proximity filters", () => {
    expect(
      PaResidentNetworkCentresSchema.safeParse({
        lat: 1.33,
      }).success,
    ).toBe(false);
    expect(
      SportSgFacilitiesSchema.safeParse({
        lng: 103.85,
      }).success,
    ).toBe(false);
  });

  it("accepts childcare vacancy filters", () => {
    expect(
      EcdaChildcareCentresSchema.safeParse({
        centreType: "CC",
        operatorType: "Private Operators",
        hasVacancy: true,
        limit: 25,
        format: "json",
      }).success,
    ).toBe(true);
  });
});
