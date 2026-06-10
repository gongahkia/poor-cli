# Relationship Graph Limits

`sg_relationship_graph` builds a shallow graph from supplied public dossier records.

Permitted nodes:

- company nodes from ACRA-style entity records
- registered-address nodes from supplied public address fields
- entity/person nodes from explicit relationship records supplied by a source

Permitted edges:

- `registered_address`: direct public record field
- `shared_registered_address`: heuristic over normalized public addresses
- `name_family`: heuristic over normalized entity-name roots
- `declared_*`: source-declared relationship records supplied in the input, such as declared director, shareholder, owner, controller, parent, subsidiary, or related-entity edges

Not supported:

- UBOs
- inferred directors or officers
- inferred shareholders
- inferred ownership/control
- inferred parent/subsidiary claims

Source-declared edges and heuristic edges are triage prompts only and must be reviewed against source records before operational use.
