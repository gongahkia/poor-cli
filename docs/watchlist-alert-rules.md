# Watchlist Alert Rules

Watchlist items are workspace-scoped and can track ACRA, GeBIZ, BCA, BOA, CEA, HSA, and HLB checks when identifiers exist. Each item stores the next run timestamp, notification channel, and alert history.

Alertable changes:

- new or removed matched module
- new gap code or upstream failure
- changed ACRA entity status
- changed license expiry/status in BCA, BOA, CEA, HSA, or HLB records
- new GeBIZ award evidence

`sg_gov_feed_items` remains the bounded source for official-feed alert expansion; hosted workers should append alerts rather than mutating prior alert records.
