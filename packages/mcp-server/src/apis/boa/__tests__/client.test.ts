import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../datagov/client.js", () => ({
  downloadDatasetCsvRows: vi.fn(),
}));

import { downloadDatasetCsvRows } from "../../datagov/client.js";
import { getBoaArchitects, getBoaArchitectureFirms } from "../client.js";

describe("BOA client", () => {
  beforeEach(() => {
    vi.mocked(downloadDatasetCsvRows).mockReset();
  });

  it("normalizes architect rows and keeps filters exact", async () => {
    vi.mocked(downloadDatasetCsvRows).mockResolvedValue([
      {
        me: "ALICE TAN",
        reg_no: "A1234",
        firm_me: "DESIGN LAB PTE LTD",
        firm_address: "1 MAIN STREET",
        firm_phone: "61234567",
      },
      {
        me: "ALICE TAN JUNIOR",
        reg_no: "A9999",
        firm_me: "DESIGN LAB PTE LTD",
        firm_address: "2 MAIN STREET",
        firm_phone: "69876543",
      },
    ] as never);

    const result = await getBoaArchitects({
      name: "alice tan",
    });

    expect(downloadDatasetCsvRows).toHaveBeenCalledWith("d_d77de0f78ca589a5c61da7a60fdee6ba", "DAILY");
    expect(result).toEqual([
      {
        architectName: "ALICE TAN",
        registrationNo: "A1234",
        firmName: "DESIGN LAB PTE LTD",
        firmAddress: "1 MAIN STREET",
        firmPhone: "61234567",
      },
    ]);
  });

  it("normalizes architecture firm rows", async () => {
    vi.mocked(downloadDatasetCsvRows).mockResolvedValue([
      {
        firm_me: "DESIGN LAB PTE LTD",
        firm_address: "1 MAIN STREET",
        firm_phone: "61234567",
        firm_fax: "",
        firm_email: "hello@designlab.sg",
      },
    ] as never);

    const result = await getBoaArchitectureFirms({
      email: "hello@designlab.sg",
    });

    expect(downloadDatasetCsvRows).toHaveBeenCalledWith("d_d5c0a4ffd076a3e40d772275619bbb66", "DAILY");
    expect(result).toEqual([
      {
        firmName: "DESIGN LAB PTE LTD",
        firmAddress: "1 MAIN STREET",
        firmPhone: "61234567",
        firmFax: null,
        firmEmail: "hello@designlab.sg",
      },
    ]);
  });
});
