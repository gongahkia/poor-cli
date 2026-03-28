export type BoaArchitectRecord = {
  readonly me: string;
  readonly reg_no: string;
  readonly firm_me: string;
  readonly firm_address: string;
  readonly firm_phone: string;
};

export type BoaNormalizedArchitectRecord = {
  readonly architectName: string;
  readonly registrationNo: string;
  readonly firmName: string | null;
  readonly firmAddress: string | null;
  readonly firmPhone: string | null;
};

export type BoaArchitectureFirmRecord = {
  readonly firm_me: string;
  readonly firm_address: string;
  readonly firm_phone: string;
  readonly firm_fax: string;
  readonly firm_email: string;
};

export type BoaNormalizedArchitectureFirmRecord = {
  readonly firmName: string;
  readonly firmAddress: string | null;
  readonly firmPhone: string | null;
  readonly firmFax: string | null;
  readonly firmEmail: string | null;
};
