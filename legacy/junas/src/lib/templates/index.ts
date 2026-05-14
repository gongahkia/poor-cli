export interface TemplateVariable {
  name: string;
  label: string;
  placeholder: string;
  type?: 'text' | 'date' | 'number';
}
export interface LegalTemplate {
  id: string;
  title: string;
  category: string;
  jurisdiction: string;
  description: string;
  variables: TemplateVariable[];
  content: string;
}

export function renderTemplate(template: LegalTemplate, values: Record<string, string>): string {
  let rendered = template.content;
  for (const v of template.variables) {
    const val = values[v.name] || `[${v.label}]`;
    rendered = rendered.replaceAll(`{{${v.name}}}`, val);
  }
  return rendered;
}

export const TEMPLATES: LegalTemplate[] = [
  {
    id: 'nda-sg',
    title: 'Non-Disclosure Agreement',
    category: 'Confidentiality',
    jurisdiction: 'Singapore',
    description: 'Mutual NDA for protecting confidential information between two parties.',
    variables: [
      { name: 'discloser', label: 'Disclosing Party', placeholder: 'ABC Pte Ltd' },
      { name: 'recipient', label: 'Receiving Party', placeholder: 'XYZ Pte Ltd' },
      { name: 'purpose', label: 'Purpose', placeholder: 'potential business collaboration' },
      { name: 'duration', label: 'Duration (years)', placeholder: '2', type: 'number' },
      { name: 'date', label: 'Date', placeholder: '2026-01-01', type: 'date' },
    ],
    content: `# NON-DISCLOSURE AGREEMENT

**Date:** {{date}}

**Between:**
1. **{{discloser}}** ("Disclosing Party")
2. **{{recipient}}** ("Receiving Party")

(collectively the "Parties")

## 1. PURPOSE

The Parties wish to explore {{purpose}} (the "Purpose") and in connection therewith, may disclose Confidential Information to each other.

## 2. CONFIDENTIAL INFORMATION

"Confidential Information" means all information disclosed by either Party to the other, whether orally, in writing, or by any other means, that is designated as confidential or that reasonably should be understood to be confidential given the nature of the information and circumstances of disclosure.

## 3. OBLIGATIONS

The Receiving Party shall:
(a) hold Confidential Information in strict confidence;
(b) not disclose Confidential Information to any third party without prior written consent;
(c) use Confidential Information solely for the Purpose;
(d) protect Confidential Information with at least the same degree of care as its own confidential information, but no less than reasonable care.

## 4. EXCLUSIONS

This Agreement does not apply to information that:
(a) is or becomes publicly available through no fault of the Receiving Party;
(b) was known to the Receiving Party before disclosure;
(c) is independently developed without use of Confidential Information;
(d) is received from a third party without restriction.

## 5. TERM

This Agreement shall remain in effect for {{duration}} years from the date hereof.

## 6. GOVERNING LAW

This Agreement shall be governed by and construed in accordance with the laws of the Republic of Singapore.

## 7. DISPUTE RESOLUTION

Any dispute arising out of this Agreement shall be referred to and resolved by arbitration administered by the Singapore International Arbitration Centre ("SIAC") in accordance with the SIAC Rules.

---

**{{discloser}}**
Name: ___________________
Signature: ___________________

**{{recipient}}**
Name: ___________________
Signature: ___________________`,
  },
  {
    id: 'employment-sg',
    title: 'Employment Agreement',
    category: 'Employment',
    jurisdiction: 'Singapore',
    description: 'Standard employment contract compliant with the Employment Act (Cap. 91).',
    variables: [
      { name: 'employer', label: 'Employer', placeholder: 'ABC Pte Ltd' },
      { name: 'employee', label: 'Employee Name', placeholder: 'John Tan' },
      { name: 'position', label: 'Position', placeholder: 'Software Engineer' },
      { name: 'salary', label: 'Monthly Salary (SGD)', placeholder: '5000', type: 'number' },
      { name: 'startDate', label: 'Start Date', placeholder: '2026-01-01', type: 'date' },
      { name: 'probation', label: 'Probation (months)', placeholder: '3', type: 'number' },
      { name: 'notice', label: 'Notice Period (months)', placeholder: '1', type: 'number' },
    ],
    content: `# EMPLOYMENT AGREEMENT

**Date:** {{startDate}}

**Between:**
1. **{{employer}}** (UEN: ___________) ("Employer")
2. **{{employee}}** (NRIC: ___________) ("Employee")

## 1. POSITION AND DUTIES

The Employer agrees to employ the Employee as **{{position}}**. The Employee shall perform such duties as reasonably assigned by the Employer.

## 2. COMMENCEMENT AND PROBATION

Employment commences on **{{startDate}}** with a probation period of **{{probation}} months**. During probation, either Party may terminate with 1 week's notice.

## 3. REMUNERATION

The Employee shall receive a gross monthly salary of **SGD {{salary}}**, payable by the last working day of each month. Salary is subject to applicable CPF contributions and tax deductions.

## 4. WORKING HOURS

Standard working hours are 44 hours per week (Monday to Friday, 9:00 AM to 6:00 PM). Overtime shall be compensated in accordance with the Employment Act (Cap. 91).

## 5. LEAVE ENTITLEMENTS

- **Annual Leave:** 14 days per calendar year (pro-rated)
- **Sick Leave:** 14 days outpatient, 60 days hospitalization per year
- **Public Holidays:** As gazetted by the Ministry of Manpower

## 6. TERMINATION

After probation, either Party may terminate this Agreement by giving **{{notice}} month(s)** written notice or salary in lieu thereof.

## 7. CONFIDENTIALITY

The Employee shall not disclose any confidential information of the Employer during or after employment.

## 8. GOVERNING LAW

This Agreement is governed by the laws of the Republic of Singapore, including the Employment Act (Cap. 91, 2009 Rev Ed).

---

**{{employer}}**
Authorised Signatory: ___________________

**{{employee}}**
Signature: ___________________`,
  },
  {
    id: 'mou-sg',
    title: 'Memorandum of Understanding',
    category: 'Partnership',
    jurisdiction: 'Singapore',
    description: 'Non-binding MOU for preliminary business arrangements.',
    variables: [
      { name: 'partyA', label: 'Party A', placeholder: 'ABC Pte Ltd' },
      { name: 'partyB', label: 'Party B', placeholder: 'XYZ Pte Ltd' },
      { name: 'subject', label: 'Subject Matter', placeholder: 'joint venture in technology development' },
      { name: 'date', label: 'Date', placeholder: '2026-01-01', type: 'date' },
      { name: 'expiry', label: 'Expiry Date', placeholder: '2026-06-30', type: 'date' },
    ],
    content: `# MEMORANDUM OF UNDERSTANDING

**Date:** {{date}}

**Between:**
1. **{{partyA}}** ("Party A")
2. **{{partyB}}** ("Party B")

## 1. PURPOSE

This MOU sets out the mutual understanding between the Parties concerning {{subject}}.

## 2. AREAS OF COOPERATION

The Parties intend to explore the following:
(a) [Describe area of cooperation]
(b) [Describe area of cooperation]

## 3. RESPONSIBILITIES

**Party A shall:**
- [Responsibility 1]

**Party B shall:**
- [Responsibility 1]

## 4. NON-BINDING NATURE

This MOU is a statement of intent only and does not create legally binding obligations, except for Clauses 5 and 6.

## 5. CONFIDENTIALITY

The Parties agree to keep the terms of this MOU and all discussions confidential.

## 6. DURATION

This MOU is effective from {{date}} until {{expiry}} unless extended by mutual written agreement.

## 7. GOVERNING LAW

This MOU shall be interpreted in accordance with the laws of Singapore.

---

**{{partyA}}** — Authorised Signatory: ___________________

**{{partyB}}** — Authorised Signatory: ___________________`,
  },
  {
    id: 'tenancy-sg',
    title: 'Tenancy Agreement',
    category: 'Property',
    jurisdiction: 'Singapore',
    description: 'Residential tenancy agreement for Singapore properties.',
    variables: [
      { name: 'landlord', label: 'Landlord', placeholder: 'Property Owner Pte Ltd' },
      { name: 'tenant', label: 'Tenant', placeholder: 'Jane Lim' },
      { name: 'address', label: 'Property Address', placeholder: '123 Orchard Road, #10-01, Singapore 238888' },
      { name: 'rent', label: 'Monthly Rent (SGD)', placeholder: '3000', type: 'number' },
      { name: 'deposit', label: 'Security Deposit (months)', placeholder: '2', type: 'number' },
      { name: 'startDate', label: 'Commencement Date', placeholder: '2026-01-01', type: 'date' },
      { name: 'term', label: 'Lease Term (years)', placeholder: '2', type: 'number' },
    ],
    content: `# TENANCY AGREEMENT

**Date:** {{startDate}}

**Between:**
1. **{{landlord}}** ("Landlord")
2. **{{tenant}}** ("Tenant")

## 1. PREMISES

The Landlord agrees to let, and the Tenant agrees to take, the premises at **{{address}}** (the "Premises").

## 2. TERM

The tenancy shall be for a period of **{{term}} year(s)** commencing on **{{startDate}}**.

## 3. RENT

The monthly rent is **SGD {{rent}}**, payable in advance on the 1st of each month.

## 4. SECURITY DEPOSIT

The Tenant shall pay a security deposit of **{{deposit}} month(s)' rent** (SGD ${`{{deposit}}`} x {{rent}}) upon execution of this Agreement. The deposit shall be refunded within 14 days of the end of the tenancy, less any deductions for damage or outstanding rent.

## 5. TENANT'S OBLIGATIONS

The Tenant shall:
(a) use the Premises for residential purposes only;
(b) keep the Premises in good condition;
(c) not sublet without written consent;
(d) pay all utility charges during the tenancy.

## 6. LANDLORD'S OBLIGATIONS

The Landlord shall:
(a) ensure the Premises are fit for habitation;
(b) carry out structural repairs;
(c) not interfere with the Tenant's quiet enjoyment.

## 7. TERMINATION

Either Party may terminate by giving 2 months' written notice. Early termination by the Tenant shall result in forfeiture of the security deposit.

## 8. GOVERNING LAW

This Agreement is governed by the laws of Singapore.

---

**{{landlord}}** — Signature: ___________________

**{{tenant}}** — Signature: ___________________`,
  },
  {
    id: 'board-resolution-sg',
    title: 'Board Resolution',
    category: 'Corporate',
    jurisdiction: 'Singapore',
    description: 'Written resolution of the board of directors under the Companies Act.',
    variables: [
      { name: 'company', label: 'Company Name', placeholder: 'ABC Pte Ltd' },
      { name: 'uen', label: 'UEN', placeholder: '202012345A' },
      { name: 'resolution', label: 'Resolution Subject', placeholder: 'appointment of new director' },
      { name: 'date', label: 'Date', placeholder: '2026-01-01', type: 'date' },
    ],
    content: `# WRITTEN RESOLUTION OF THE BOARD OF DIRECTORS

**{{company}}** (UEN: {{uen}})

(Incorporated in the Republic of Singapore)

**Date:** {{date}}

Pursuant to the Articles of Association of the Company and Section 184A of the Companies Act 1967 (2020 Revised Edition), the undersigned, being all the directors of the Company, hereby pass the following resolution:

## RESOLUTION

**IT IS RESOLVED THAT** {{resolution}}.

## CONFIRMATION

This resolution shall take effect from the date first written above and shall be as valid as if it had been passed at a duly convened meeting of the Board of Directors.

---

**Director:** ___________________
Name:
Date:

**Director:** ___________________
Name:
Date:`,
  },
  {
    id: 'share-transfer-sg',
    title: 'Share Transfer Form',
    category: 'Corporate',
    jurisdiction: 'Singapore',
    description: 'Instrument of transfer for ordinary shares in a Singapore company.',
    variables: [
      { name: 'company', label: 'Company Name', placeholder: 'ABC Pte Ltd' },
      { name: 'transferor', label: 'Transferor', placeholder: 'John Tan' },
      { name: 'transferee', label: 'Transferee', placeholder: 'Jane Lim' },
      { name: 'shares', label: 'Number of Shares', placeholder: '1000', type: 'number' },
      { name: 'pricePerShare', label: 'Price Per Share (SGD)', placeholder: '1.00' },
      { name: 'date', label: 'Date', placeholder: '2026-01-01', type: 'date' },
    ],
    content: `# INSTRUMENT OF TRANSFER OF SHARES

**Date:** {{date}}

## DETAILS

| Field | Value |
|-------|-------|
| Company | **{{company}}** |
| Transferor | **{{transferor}}** |
| Transferee | **{{transferee}}** |
| Number of Shares | **{{shares}}** ordinary shares |
| Consideration | **SGD {{pricePerShare}}** per share |

## TRANSFER

I, **{{transferor}}** (the "Transferor"), in consideration of the sum of SGD ({{shares}} x {{pricePerShare}}) paid to me by **{{transferee}}** (the "Transferee"), hereby transfer to the Transferee **{{shares}}** ordinary shares in **{{company}}**, subject to the conditions on which I held the same.

I, **{{transferee}}**, hereby accept the said shares subject to the said conditions.

## STAMP DUTY

This transfer is subject to stamp duty under the Stamp Duties Act 1929 (2020 Revised Edition).

---

**Transferor:** ___________________
Name: {{transferor}}
Date:

**Transferee:** ___________________
Name: {{transferee}}
Date:

**Witness:** ___________________
Name:
Date:`,
  },
];
