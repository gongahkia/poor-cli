export type LtaBusArrivalResponse = {
  readonly BusStopCode: string;
  readonly Services: readonly LtaBusArrivalService[];
};

export type LtaBusArrivalService = {
  readonly ServiceNo: string;
  readonly Operator: string;
  readonly NextBus: LtaBusArrivalTiming;
  readonly NextBus2: LtaBusArrivalTiming;
  readonly NextBus3: LtaBusArrivalTiming;
};

export type LtaBusArrivalTiming = {
  readonly OriginCode?: string;
  readonly DestinationCode?: string;
  readonly EstimatedArrival?: string;
  readonly Monitored?: number;
  readonly Latitude?: string;
  readonly Longitude?: string;
  readonly VisitNumber?: string;
  readonly Load?: string;
  readonly Feature?: string;
  readonly Type?: string;
};

export type LtaNormalizedBusArrival = {
  readonly busStopCode: string;
  readonly serviceNo: string;
  readonly operator: string;
  readonly arrivals: readonly {
    readonly ordinal: 1 | 2 | 3;
    readonly estimatedArrival: string | null;
    readonly load: string | null;
    readonly feature: string | null;
    readonly type: string | null;
    readonly monitored: boolean;
    readonly visitNumber: string | null;
    readonly originCode: string | null;
    readonly destinationCode: string | null;
    readonly lat: number | null;
    readonly lng: number | null;
  }[];
};

export type LtaTrainAlertLine = {
  readonly Status?: number;
  readonly Line?: string;
  readonly Direction?: string;
  readonly Stations?: string;
  readonly FreePublicBus?: string;
  readonly FreeMRTShuttle?: string;
  readonly MRTShuttleDirection?: string;
};

export type LtaTrainAlertMessage = {
  readonly Content?: string;
  readonly CreatedDate?: string;
};

export type LtaTrainAlertsResponse = {
  readonly value?: readonly LtaTrainAlertLine[];
  readonly Message?: readonly LtaTrainAlertMessage[];
};

export type LtaNormalizedTrainAlert = {
  readonly line: string;
  readonly status: number | null;
  readonly direction: string | null;
  readonly stations: readonly string[];
  readonly freePublicBus: readonly string[];
  readonly freeMrtShuttle: readonly string[];
  readonly mrtShuttleDirection: string | null;
};

export type LtaNormalizedTrainAlertMessage = {
  readonly content: string;
  readonly createdDate: string | null;
};

export type LtaTrafficIncident = {
  readonly Type?: string;
  readonly Latitude?: number | string;
  readonly Longitude?: number | string;
  readonly Message?: string;
};

export type LtaTrafficIncidentsResponse = {
  readonly value?: readonly LtaTrafficIncident[];
};

export type LtaNormalizedTrafficIncident = {
  readonly type: string;
  readonly lat: number | null;
  readonly lng: number | null;
  readonly message: string;
};
