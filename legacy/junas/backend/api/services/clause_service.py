"""Legal clause library ported from Junas clauses/index.ts."""
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class LegalClause:
    id: str
    name: str
    category: str
    jurisdiction: str
    description: str
    standard: str
    aggressive: str
    balanced: str
    protective: str
    notes: str

CLAUSE_LIBRARY: list[LegalClause] = [
    LegalClause(
        id="force-majeure-sg", name="Force Majeure", category="Risk Allocation", jurisdiction="Singapore",
        description="Excuses performance when prevented by events beyond reasonable control.",
        standard="Neither Party shall be liable for any failure or delay in performing its obligations where such failure or delay results from Force Majeure Events including but not limited to acts of God, war, terrorism, pandemic, government action, fire, flood, earthquake, or other circumstances beyond the reasonable control of the affected Party.",
        aggressive="The Supplier shall not be excused from performance by reason of any Force Majeure Event. The Supplier shall use all reasonable endeavours to mitigate the effects of any such event and resume performance at the earliest opportunity.",
        balanced="Neither Party shall be liable for failure to perform due to Force Majeure Events. The affected Party shall notify the other within 7 days and use reasonable efforts to mitigate. If the event continues for more than 90 days, either Party may terminate without liability.",
        protective="The Company shall not be liable for any delay or failure in performance caused by circumstances beyond its reasonable control, including but not limited to pandemics, supply chain disruptions, government orders, natural disasters, labour disputes, and cyber-attacks. No obligation to mitigate shall apply.",
        notes="Singapore courts interpret force majeure strictly — the clause must be explicitly drafted and the event must be specifically covered. See RDC Concrete Pte Ltd v Sato Kogyo (S) Pte Ltd [2007] 4 SLR(R) 413.",
    ),
    LegalClause(
        id="limitation-liability-sg", name="Limitation of Liability", category="Liability", jurisdiction="Singapore",
        description="Caps total liability and excludes consequential damages.",
        standard="The total aggregate liability of either Party under this Agreement shall not exceed the total fees paid or payable in the 12 months preceding the claim. Neither Party shall be liable for any indirect, consequential, special, or incidental damages.",
        aggressive="The Supplier's total aggregate liability shall not exceed SGD 100. The Supplier shall not be liable for any loss of profit, revenue, data, business, or anticipated savings, whether direct or indirect.",
        balanced="Each Party's total aggregate liability shall not exceed the greater of (a) total fees paid in the preceding 12 months or (b) SGD 50,000. This limitation shall not apply to breaches of confidentiality, IP infringement, or gross negligence.",
        protective="The Service Provider's total liability shall not exceed the fees actually received for the specific deliverable giving rise to the claim. The Client acknowledges that the Service Provider shall have no liability for any consequential, indirect, or punitive damages.",
        notes="Under UCTA (Cap. 396), limitation clauses must satisfy the reasonableness test. Clauses attempting to limit liability for death or personal injury caused by negligence are void.",
    ),
    LegalClause(
        id="indemnification-sg", name="Indemnification", category="Liability", jurisdiction="Singapore",
        description="Obligation to compensate the other party for specified losses.",
        standard="Each Party shall indemnify and hold harmless the other Party from and against all claims, damages, losses, and expenses (including reasonable legal fees) arising from any breach of this Agreement or any negligent or wrongful act or omission.",
        aggressive="The Vendor shall fully indemnify, defend, and hold harmless the Client and its affiliates from any and all claims, losses, liabilities, damages, costs, and expenses (including legal fees on a full indemnity basis) arising directly or indirectly from the Vendor's performance or failure to perform.",
        balanced="Each Party shall indemnify the other against third-party claims arising from: (a) breach of this Agreement, (b) negligence or wilful misconduct, (c) infringement of intellectual property rights. The indemnifying Party shall have the right to control the defence.",
        protective="The Client shall indemnify the Service Provider against all claims by third parties arising from the Client's use of the deliverables, except to the extent caused by the Service Provider's gross negligence or wilful misconduct.",
        notes="Singapore law permits contractual indemnities. The indemnifying party should have control of defence. Consider whether indemnity survives termination.",
    ),
    LegalClause(
        id="confidentiality-sg", name="Confidentiality", category="Information Protection", jurisdiction="Singapore",
        description="Protects disclosed confidential information from unauthorized use.",
        standard="Each Party shall keep confidential all information received from the other Party that is designated as confidential or that reasonably should be understood to be confidential. This obligation shall survive for 3 years after termination.",
        aggressive="The Receiving Party shall keep strictly confidential all information disclosed by the Disclosing Party, in any form, and shall not disclose such information to any person without prior written consent. The obligations herein shall survive in perpetuity.",
        balanced="Confidential Information excludes information that: (a) is publicly available, (b) was known prior to disclosure, (c) is independently developed, (d) is disclosed by a third party without restriction. Obligations survive for 3 years post-termination.",
        protective="All information disclosed by the Company is deemed Confidential Information. The Recipient may disclose only to employees on a need-to-know basis under equivalent obligations. No reverse engineering permitted.",
        notes="Singapore does not have a standalone trade secrets statute. Protection relies on contract (this clause) and the equitable doctrine of breach of confidence.",
    ),
    LegalClause(
        id="ip-ownership-sg", name="Intellectual Property Ownership", category="Intellectual Property", jurisdiction="Singapore",
        description="Allocates ownership of intellectual property created under the agreement.",
        standard="All intellectual property rights in deliverables created under this Agreement shall vest in the Client upon payment. The Service Provider retains rights in pre-existing IP and grants a non-exclusive licence for its use in the deliverables.",
        aggressive="All intellectual property rights (including moral rights to the extent waivable) in any work product shall vest absolutely in the Client from the moment of creation. The Service Provider assigns all right, title, and interest worldwide.",
        balanced="The Client owns all IP in bespoke deliverables upon full payment. The Service Provider retains ownership of pre-existing IP, tools, and methodologies, granting the Client a perpetual, non-exclusive licence. Joint IP shall be co-owned.",
        protective="The Service Provider retains all intellectual property rights in the deliverables. The Client is granted a limited, non-exclusive, non-transferable licence to use the deliverables for its internal business purposes only.",
        notes="Under the Copyright Act 2021, the default rule is that the author owns copyright unless created in the course of employment. Assignments must be in writing.",
    ),
    LegalClause(
        id="non-compete-sg", name="Non-Compete / Restraint of Trade", category="Employment", jurisdiction="Singapore",
        description="Restricts competition after termination of employment or business relationship.",
        standard="The Employee shall not, for a period of 12 months following termination, engage in any business that competes with the Employer within Singapore.",
        aggressive="The Employee shall not, for 24 months following termination, directly or indirectly engage in, be employed by, consult for, or have any interest in any business competitive with the Employer, anywhere in Southeast Asia.",
        balanced="The Employee shall not, for 6 months following termination, solicit or deal with any client of the Employer with whom the Employee had material contact in the final 12 months. This restriction is limited to Singapore.",
        protective="The Employee acknowledges that no non-compete restriction shall apply after termination. The Employee shall remain bound only by confidentiality obligations.",
        notes="Singapore courts apply the restraint of trade doctrine strictly. Restrictions must be reasonable in scope, duration, and geography. See Smile Inc Dental Surgeons Pte Ltd v Lui Andrew Stewart [2012] 4 SLR 308.",
    ),
]

_CLAUSE_INDEX: dict[str, LegalClause] = {c.id: c for c in CLAUSE_LIBRARY}

def get_clause(clause_id: str) -> LegalClause | None:
    return _CLAUSE_INDEX.get(clause_id)

def search_clauses(query: str = "", jurisdiction: str = "", category: str = "") -> list[LegalClause]:
    results = CLAUSE_LIBRARY
    if jurisdiction:
        results = [c for c in results if c.jurisdiction.lower() == jurisdiction.lower()]
    if category:
        results = [c for c in results if c.category.lower() == category.lower()]
    if query:
        q = query.lower()
        results = [c for c in results if q in c.name.lower() or q in c.category.lower() or q in c.description.lower()]
    return results

def get_tone(clause: LegalClause, tone: str) -> str:
    return getattr(clause, tone, clause.standard)
