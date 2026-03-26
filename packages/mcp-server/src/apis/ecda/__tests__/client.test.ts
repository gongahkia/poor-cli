import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../datagov/client.js", () => ({
  downloadDatasetCsvRows: vi.fn(),
  downloadDatasetGeoJson: vi.fn(),
}));

import { downloadDatasetCsvRows, downloadDatasetGeoJson } from "../../datagov/client.js";
import { getEcdaChildcareCentres } from "../client.js";

const geojsonFixture = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [103.851, 1.284] },
      properties: {
        NAME: "MY FIRST SKOOL @ ONE RAFFLES PLACE",
        ADDRESSPOSTALCODE: "048616",
        ADDRESSSTREETNAME: "1 Raffles Place",
        FMEL_UPD_D: "20240417181750",
      },
    },
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [103.85146, 1.28413] },
      properties: {
        NAME: "Little Seeds Preschool",
        ADDRESSPOSTALCODE: "",
        ADDRESSSTREETNAME: "5 Raffles Place",
        FMEL_UPD_D: "20240417181750",
      },
    },
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [103.8537, 1.2864] },
      properties: {
        NAME: "Unmatched Childcare",
        ADDRESSPOSTALCODE: "049178",
        ADDRESSSTREETNAME: "1 Fullerton Square",
        FMEL_UPD_D: "20240417181750",
      },
    },
  ],
} as const;

const csvFixture = [
  {
    tp_code: "CC",
    centre_code: "CC0001",
    centre_name: "MY FIRST SKOOL @ ONE RAFFLES PLACE",
    organisation_code: "ORG001",
    organisation_description: "PAP Community Foundation",
    service_model: "CHILD CARE / INFANT CARE",
    centre_address: "1 Raffles Place, #01-01",
    postal_code: "048616",
    centre_contact_no: "61234567",
    centre_email_address: "info@myfirstskool.sg",
    centre_website: "https://www.myfirstskool.com",
    website_lifesg: "",
    contactno_lifesg: "",
    emailaddress_lifesg: "",
    infant_vacancy_current_month: "Available",
    pg_vacancy_current_month: "Limited",
    n1_vacancy_current_month: "Full",
    n2_vacancy_current_month: "Full",
    k1_vacancy_current_month: "Available",
    k2_vacancy_current_month: "Full",
    last_updated: "2026-03-20",
  },
  {
    tp_code: "CC",
    centre_code: "CC0002",
    centre_name: "Little Seeds Preschool",
    organisation_code: "ORG002",
    organisation_description: "Little Seeds",
    service_model: "CHILD CARE",
    centre_address: "5 Raffles Place, #02-01",
    postal_code: "",
    centre_contact_no: "62345678",
    centre_email_address: "hello@littleseeds.sg",
    centre_website: "https://www.littleseeds.sg",
    website_lifesg: "",
    contactno_lifesg: "",
    emailaddress_lifesg: "",
    infant_vacancy_current_month: "Full",
    pg_vacancy_current_month: "Full",
    n1_vacancy_current_month: "Full",
    n2_vacancy_current_month: "Full",
    k1_vacancy_current_month: "Full",
    k2_vacancy_current_month: "Full",
    last_updated: "2026-03-19",
  },
] as const;

describe("ECDA childcare client", () => {
  beforeEach(() => {
    vi.mocked(downloadDatasetGeoJson).mockReset();
    vi.mocked(downloadDatasetCsvRows).mockReset();
    vi.mocked(downloadDatasetGeoJson).mockResolvedValue(geojsonFixture as never);
    vi.mocked(downloadDatasetCsvRows).mockResolvedValue(csvFixture as never);
  });

  it("joins childcare GeoJSON and listing rows by postal code first, then name", async () => {
    const records = await getEcdaChildcareCentres({});

    expect(downloadDatasetGeoJson).toHaveBeenCalledWith("d_5d668e3f544335f8028f546827b773b4", "DAILY");
    expect(downloadDatasetCsvRows).toHaveBeenCalledWith("d_696c994c50745b079b3684f0e90ffc53", "DAILY");
    expect(records).toHaveLength(3);

    expect(records[0]).toMatchObject({
      name: "Little Seeds Preschool",
      centreCode: "CC0002",
      centreType: "CC",
      operatorType: "Little Seeds",
      hasVacancy: false,
      postalCode: null,
      lastUpdatedAt: "2026-03-19",
    });

    expect(records[1]).toMatchObject({
      name: "MY FIRST SKOOL @ ONE RAFFLES PLACE",
      centreCode: "CC0001",
      centreType: "CC",
      operatorType: "PAP Community Foundation",
      serviceModel: "CHILD CARE / INFANT CARE",
      hasVacancy: true,
      infantVacancyCurrentMonth: "available",
      playgroupVacancyCurrentMonth: "limited",
      k1VacancyCurrentMonth: "available",
      postalCode: "048616",
    });

    expect(records[2]).toMatchObject({
      name: "Unmatched Childcare",
      centreCode: null,
      hasVacancy: null,
      lastUpdatedAt: "2024-04-17T18:17:50+08:00",
    });
  });

  it("filters childcare records by centre type, operator, and vacancy signal", async () => {
    const records = await getEcdaChildcareCentres({
      centreType: "CC",
      operatorType: "pap community",
      hasVacancy: true,
    });

    expect(records).toEqual([
      expect.objectContaining({
        name: "MY FIRST SKOOL @ ONE RAFFLES PLACE",
        centreCode: "CC0001",
        hasVacancy: true,
      }),
    ]);
  });
});
