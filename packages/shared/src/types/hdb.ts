export type HdbResaleRecord = {
  readonly id?: string;
  readonly month: string;
  readonly town: string;
  readonly flat_type: string;
  readonly block: string;
  readonly street_name: string;
  readonly storey_range: string;
  readonly floor_area_sqm: string;
  readonly flat_model: string;
  readonly lease_commence_date: string;
  readonly remaining_lease: string;
  readonly resale_price: string;
};

export type HdbNormalizedResaleRecord = {
  readonly month: string;
  readonly town: string;
  readonly flatType: string;
  readonly block: string;
  readonly streetName: string;
  readonly storeyRange: string;
  readonly floorAreaSqm: number | null;
  readonly flatModel: string;
  readonly leaseCommenceDate: number | null;
  readonly remainingLease: string;
  readonly resalePrice: number | null;
};

export type HdbRentalRecord = {
  readonly id?: string;
  readonly rent_approval_date: string;
  readonly town: string;
  readonly block: string;
  readonly street_name: string;
  readonly flat_type: string;
  readonly monthly_rent: string;
};

export type HdbNormalizedRentalRecord = {
  readonly approvalMonth: string;
  readonly town: string;
  readonly block: string;
  readonly streetName: string;
  readonly flatType: string;
  readonly monthlyRent: number | null;
};
