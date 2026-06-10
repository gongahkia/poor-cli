import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("../../datagov/client.js", () => ({
  downloadDatasetXlsxRows: vi.fn(),
}));

import { downloadDatasetXlsxRows } from "../../datagov/client.js";
import { getWaterLevels } from "../client.js";

describe("PUB client", () => {
  beforeEach(() => {
    vi.mocked(downloadDatasetXlsxRows).mockReset();
  });

  it("normalizes current PUB water-level sensor XLSX rows without inventing live readings", async () => {
    vi.mocked(downloadDatasetXlsxRows).mockResolvedValue([
      {
        "Station ID": "CWS186",
        "Station Name": "Eng Neo Ave OD (Vanda Lk u/s culvert)",
        X: "24084.3225173761",
        Y: "34974.3647553378",
      },
      {
        "Station ID": "CWS192",
        "Station Name": "Happy Ave OD (Jln Gembira)",
        X: "33422.2991199334",
        Y: "34953.9561102139",
      },
    ]);

    const records = await getWaterLevels({ station: "Eng Neo", limit: 5 });

    expect(downloadDatasetXlsxRows).toHaveBeenCalledWith("d_31333fa5cf0834f012d840365b336610", "STATIC");
    expect(records).toEqual([
      {
        station: "Eng Neo Ave OD (Vanda Lk u/s culvert)",
        stationId: "CWS186",
        easting: 24084.3225173761,
        northing: 34974.3647553378,
        date: null,
        time: null,
        waterLevel: null,
        lat: null,
        lng: null,
        url: "https://data.gov.sg/datasets/d_31333fa5cf0834f012d840365b336610/view",
        lastUpdatedAt: null,
      },
    ]);
  });
});
