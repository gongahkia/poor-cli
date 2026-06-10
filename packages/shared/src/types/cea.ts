export type CeaSalespersonRecord = {
  readonly salesperson_name: string;
  readonly registration_no: string;
  readonly registration_start_date: string;
  readonly registration_end_date: string;
  readonly estate_agent_name: string;
  readonly estate_agent_license_no: string;
};

export type CeaNormalizedSalespersonRecord = {
  readonly salespersonName: string;
  readonly registrationNo: string;
  readonly registrationStartDate: string;
  readonly registrationEndDate: string;
  readonly estateAgentName: string;
  readonly estateAgentLicenseNo: string;
};
