# Hotel Operator Lookup

## Prompt

```text
Look up Marina Bay Sands and return the keeper, room count, and any direct company context that can be checked next.
```

## What It Exercises

- resource: `sg://workflows`
- direct tool: `sg_hlb_hotels`
- supporting tool: `sg_acra_entities`
- routed workflow: `sg_query`

## Why The Workflow Is Better Than Raw Calls

Raw hospitality diligence means calling the hotel directory first and then deciding whether the keeper should be widened into company context.

The bounded workflow keeps the output honest by:

- using HLB hotel and keeper facts as the primary source
- avoiding any travel-planning or recommendation claims
- returning direct next steps when the caller wants wider entity verification

## Sample Output Shape

```json
{
  "status": "completed",
  "mode": "execute",
  "workflow": "hotel_operator_lookup",
  "intent": "business",
  "toolsUsed": ["sg_hlb_hotels"],
  "resultSummary": {
    "level": "informational",
    "headline": "Hotel lookup completed with HLB keeper and room-count evidence."
  },
  "nextActions": [
    {
      "tool": "sg_acra_entities",
      "reason": "Verify the keeper against the company register when wider entity context is needed.",
      "input": { "entityName": "MARINA BAY SANDS PTE. LTD." }
    }
  ]
}
```
