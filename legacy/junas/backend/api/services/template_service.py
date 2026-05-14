"""Legal template library ported from Junas templates/index.ts."""
from __future__ import annotations
import re
from dataclasses import dataclass, field

@dataclass
class TemplateVariable:
    name: str
    label: str
    placeholder: str
    var_type: str = "text"  # text | date | number

@dataclass
class LegalTemplate:
    id: str
    title: str
    category: str
    jurisdiction: str
    description: str
    variables: list[TemplateVariable]
    content: str

def render_template(template: LegalTemplate, values: dict[str, str]) -> str:
    rendered = template.content
    for v in template.variables:
        val = values.get(v.name) or f"[{v.label}]"
        rendered = rendered.replace(f"{{{{{v.name}}}}}", val)
    return rendered

TEMPLATES: list[LegalTemplate] = [
    LegalTemplate(
        id="nda-sg", title="Non-Disclosure Agreement", category="Confidentiality", jurisdiction="Singapore",
        description="Mutual NDA for protecting confidential information between two parties.",
        variables=[
            TemplateVariable("discloser", "Disclosing Party", "ABC Pte Ltd"),
            TemplateVariable("recipient", "Receiving Party", "XYZ Pte Ltd"),
            TemplateVariable("purpose", "Purpose", "potential business collaboration"),
            TemplateVariable("duration", "Duration (years)", "2", "number"),
            TemplateVariable("date", "Date", "2026-01-01", "date"),
        ],
        content="""# NON-DISCLOSURE AGREEMENT

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
Signature: ___________________""",
    ),
    LegalTemplate(
        id="employment-sg", title="Employment Agreement", category="Employment", jurisdiction="Singapore",
        description="Standard employment contract compliant with the Employment Act (Cap. 91).",
        variables=[
            TemplateVariable("employer", "Employer", "ABC Pte Ltd"),
            TemplateVariable("employee", "Employee Name", "John Tan"),
            TemplateVariable("position", "Position", "Software Engineer"),
            TemplateVariable("salary", "Monthly Salary (SGD)", "5000", "number"),
            TemplateVariable("startDate", "Start Date", "2026-01-01", "date"),
            TemplateVariable("probation", "Probation (months)", "3", "number"),
            TemplateVariable("notice", "Notice Period (months)", "1", "number"),
        ],
        content="""# EMPLOYMENT AGREEMENT

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
Signature: ___________________""",
    ),
    LegalTemplate(
        id="mou-sg", title="Memorandum of Understanding", category="Partnership", jurisdiction="Singapore",
        description="Non-binding MOU for preliminary business arrangements.",
        variables=[
            TemplateVariable("partyA", "Party A", "ABC Pte Ltd"),
            TemplateVariable("partyB", "Party B", "XYZ Pte Ltd"),
            TemplateVariable("subject", "Subject Matter", "joint venture in technology development"),
            TemplateVariable("date", "Date", "2026-01-01", "date"),
            TemplateVariable("expiry", "Expiry Date", "2026-06-30", "date"),
        ],
        content="""# MEMORANDUM OF UNDERSTANDING

**Date:** {{date}}

**Between:**
1. **{{partyA}}** ("Party A")
2. **{{partyB}}** ("Party B")

## 1. PURPOSE
This MOU sets out the mutual understanding between the Parties concerning {{subject}}.

## 2. NON-BINDING NATURE
This MOU is a statement of intent only and does not create legally binding obligations, except for Clauses on confidentiality and governing law.

## 3. DURATION
This MOU is effective from {{date}} until {{expiry}} unless extended by mutual written agreement.

## 4. GOVERNING LAW
This MOU shall be interpreted in accordance with the laws of Singapore.

---
**{{partyA}}** — Authorised Signatory: ___________________
**{{partyB}}** — Authorised Signatory: ___________________""",
    ),
    LegalTemplate(
        id="tenancy-sg", title="Tenancy Agreement", category="Property", jurisdiction="Singapore",
        description="Residential tenancy agreement for Singapore properties.",
        variables=[
            TemplateVariable("landlord", "Landlord", "Property Owner Pte Ltd"),
            TemplateVariable("tenant", "Tenant", "Jane Lim"),
            TemplateVariable("address", "Property Address", "123 Orchard Road, #10-01, Singapore 238888"),
            TemplateVariable("rent", "Monthly Rent (SGD)", "3000", "number"),
            TemplateVariable("deposit", "Security Deposit (months)", "2", "number"),
            TemplateVariable("startDate", "Commencement Date", "2026-01-01", "date"),
            TemplateVariable("term", "Lease Term (years)", "2", "number"),
        ],
        content="""# TENANCY AGREEMENT

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
The Tenant shall pay a security deposit of **{{deposit}} month(s)' rent** upon execution of this Agreement.

## 5. GOVERNING LAW
This Agreement is governed by the laws of Singapore.

---
**{{landlord}}** — Signature: ___________________
**{{tenant}}** — Signature: ___________________""",
    ),
    LegalTemplate(
        id="board-resolution-sg", title="Board Resolution", category="Corporate", jurisdiction="Singapore",
        description="Written resolution of the board of directors under the Companies Act.",
        variables=[
            TemplateVariable("company", "Company Name", "ABC Pte Ltd"),
            TemplateVariable("uen", "UEN", "202012345A"),
            TemplateVariable("resolution", "Resolution Subject", "appointment of new director"),
            TemplateVariable("date", "Date", "2026-01-01", "date"),
        ],
        content="""# WRITTEN RESOLUTION OF THE BOARD OF DIRECTORS

**{{company}}** (UEN: {{uen}})
(Incorporated in the Republic of Singapore)
**Date:** {{date}}

Pursuant to the Articles of Association of the Company and Section 184A of the Companies Act 1967 (2020 Revised Edition), the undersigned, being all the directors of the Company, hereby pass the following resolution:

## RESOLUTION
**IT IS RESOLVED THAT** {{resolution}}.

---
**Director:** ___________________
Name:
Date:""",
    ),
    LegalTemplate(
        id="share-transfer-sg", title="Share Transfer Form", category="Corporate", jurisdiction="Singapore",
        description="Instrument of transfer for ordinary shares in a Singapore company.",
        variables=[
            TemplateVariable("company", "Company Name", "ABC Pte Ltd"),
            TemplateVariable("transferor", "Transferor", "John Tan"),
            TemplateVariable("transferee", "Transferee", "Jane Lim"),
            TemplateVariable("shares", "Number of Shares", "1000", "number"),
            TemplateVariable("pricePerShare", "Price Per Share (SGD)", "1.00"),
            TemplateVariable("date", "Date", "2026-01-01", "date"),
        ],
        content="""# INSTRUMENT OF TRANSFER OF SHARES

**Date:** {{date}}

| Field | Value |
|-------|-------|
| Company | **{{company}}** |
| Transferor | **{{transferor}}** |
| Transferee | **{{transferee}}** |
| Number of Shares | **{{shares}}** ordinary shares |
| Consideration | **SGD {{pricePerShare}}** per share |

I, **{{transferor}}** (the "Transferor"), in consideration of the sum paid to me by **{{transferee}}** (the "Transferee"), hereby transfer to the Transferee **{{shares}}** ordinary shares in **{{company}}**.

This transfer is subject to stamp duty under the Stamp Duties Act 1929 (2020 Revised Edition).

---
**Transferor:** ___________________ Name: {{transferor}}
**Transferee:** ___________________ Name: {{transferee}}
**Witness:** ___________________ Name:""",
    ),
]

_TEMPLATE_INDEX: dict[str, LegalTemplate] = {t.id: t for t in TEMPLATES}

def get_template(template_id: str) -> LegalTemplate | None:
    return _TEMPLATE_INDEX.get(template_id)

def list_templates(jurisdiction: str = "", category: str = "") -> list[LegalTemplate]:
    results = TEMPLATES
    if jurisdiction:
        results = [t for t in results if t.jurisdiction.lower() == jurisdiction.lower()]
    if category:
        results = [t for t in results if t.category.lower() == category.lower()]
    return results
