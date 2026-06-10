export type NeaRealtimeResponse<TData> = {
  readonly code: number;
  readonly data: TData;
  readonly errorMsg: string;
};

export type NeaForecastAreaMetadata = {
  readonly name: string;
  readonly label_location: {
    readonly latitude: number;
    readonly longitude: number;
  };
};

export type NeaForecastItem = {
  readonly update_timestamp: string;
  readonly timestamp: string;
  readonly valid_period: {
    readonly start: string;
    readonly end: string;
    readonly text: string;
  };
  readonly forecasts: readonly {
    readonly area: string;
    readonly forecast: string;
  }[];
};

export type NeaForecastResponse = NeaRealtimeResponse<{
  readonly area_metadata: readonly NeaForecastAreaMetadata[];
  readonly items: readonly NeaForecastItem[];
}>;

export type NeaNormalizedForecast = {
  readonly area: string;
  readonly forecast: string;
  readonly validFrom: string;
  readonly validTo: string;
  readonly validText: string;
  readonly updatedAt: string;
  readonly lat: number | null;
  readonly lng: number | null;
};

export type NeaPsiItem = {
  readonly date: string;
  readonly updatedTimestamp: string;
  readonly timestamp: string;
  readonly readings: Readonly<Record<string, Readonly<Record<string, number>>>>;
};

export type NeaPsiResponse = NeaRealtimeResponse<{
  readonly regionMetadata: readonly {
    readonly name: string;
    readonly labelLocation: {
      readonly latitude: number;
      readonly longitude: number;
    };
  }[];
  readonly items: readonly NeaPsiItem[];
}>;

export type NeaPm25Response = NeaRealtimeResponse<{
  readonly regionMetadata: readonly {
    readonly name: string;
    readonly labelLocation: {
      readonly latitude: number;
      readonly longitude: number;
    };
  }[];
  readonly items: readonly {
    readonly date: string;
    readonly updatedTimestamp: string;
    readonly timestamp: string;
    readonly readings: {
      readonly pm25_one_hourly: Readonly<Record<string, number>>;
    };
  }[];
}>;

export type NeaNormalizedAirQuality = {
  readonly region: string;
  readonly psi24h: number | null;
  readonly pm25OneHourly: number | null;
  readonly pm25TwentyFourHourly: number | null;
  readonly updatedAt: string;
  readonly lat: number | null;
  readonly lng: number | null;
};

export type NeaRainfallResponse = NeaRealtimeResponse<{
  readonly readingType: string;
  readonly readingUnit: string;
  readonly stations: readonly {
    readonly id: string;
    readonly deviceId: string;
    readonly name: string;
    readonly location: {
      readonly latitude: number;
      readonly longitude: number;
    };
  }[];
  readonly readings: readonly {
    readonly timestamp: string;
    readonly data: readonly {
      readonly stationId: string;
      readonly value: number;
    }[];
  }[];
}>;

export type NeaNormalizedRainfall = {
  readonly stationId: string;
  readonly stationName: string;
  readonly value: number;
  readonly unit: string;
  readonly timestamp: string;
  readonly lat: number | null;
  readonly lng: number | null;
};
