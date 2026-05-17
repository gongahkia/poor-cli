# Adverse Media Lite Feed Scope

`sg_adverse_media_lite` searches bounded official Singapore public feeds for keyword evidence. It is intentionally not a general news monitor.

Included feed families:

- SFA food alerts and media releases
- NEA news updates
- MPA media releases
- URA media releases

Success criteria:

- source URLs and observed freshness are preserved per feed
- feed failures become gaps instead of aborting the whole artifact
- confidence is limited to `official_feed_keyword_match`
- no sentiment, culpability, adverse-event classification, or unsupported NLP is performed
