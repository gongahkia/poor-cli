import type { CivicDirectoryRecord } from "./civic.js";

export type HlbHotelRecord = CivicDirectoryRecord & {
  readonly keeperName: string | null;
  readonly totalRooms: number | null;
  readonly url: string | null;
  readonly incCrc: string | null;
};
