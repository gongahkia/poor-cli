# Relationship Graph Limits

`sg_relationship_graph` builds a shallow graph from supplied public dossier records.

Permitted nodes:

- company nodes from ACRA-style entity records
- registered-address nodes from supplied public address fields

Permitted edges:

- `registered_address`: direct public record field
- `shared_registered_address`: heuristic over normalized public addresses
- `name_family`: heuristic over normalized entity-name roots

Not supported:

- UBOs
- directors or officers
- shareholders
- ownership/control
- parent/subsidiary claims

Heuristic edges are triage prompts only and must be reviewed against source records before operational use.
