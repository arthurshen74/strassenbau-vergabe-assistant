# entity-rule-management Specification

## Purpose
Storage, validation, and administration of EntityRuler rules: persisting labelled spaCy patterns, seeding an initial ruleset, validating patterns against spaCy before write, editing/toggling/removing rules, discovering existing labels, and managing all of this through a dedicated admin page.

## Requirements

### Requirement: Entity rules are stored and queryable
The system SHALL persist EntityRuler rules with a label, a spaCy pattern (a string or a list of token-attribute objects), an optional grouping identifier, and an enabled flag, and SHALL support listing all rules and fetching one by id.

#### Scenario: Listing all rules
- **WHEN** `GET /entity-rules` is called
- **THEN** every rule is returned regardless of its enabled state, ordered by label then created_at

### Requirement: The initial ruleset seeds once from the authored JSON fixture
The system SHALL provide an idempotent seed script that imports `server/shared/services/nlp/entity_rules.json` into the table, keyed so re-running the script does not create duplicates.

#### Scenario: Re-running the seed script
- **WHEN** the seed script runs a second time against a database already containing the seeded rules
- **THEN** the rule count is unchanged after the second run

### Requirement: A rule's pattern is validated against spaCy before it is persisted
The system SHALL compile a candidate label+pattern against a scratch spaCy pipeline before create or update; a compile failure SHALL reject the write with the underlying spaCy error message and SHALL NOT reach the database or the live pipeline.

#### Scenario: Invalid pattern rejected
- **WHEN** a rule is submitted with a pattern spaCy cannot compile (e.g. an unknown token attribute)
- **THEN** the API responds 422 with spaCy's error message and no row is written

#### Scenario: Valid pattern accepted
- **WHEN** a rule is submitted with a pattern that compiles
- **THEN** the rule is persisted and returned with a generated id

### Requirement: Rules can be edited, toggled, and removed
The system SHALL support partial updates (label, pattern, pattern_id, enabled) and deletion of an existing rule by id.

#### Scenario: Disabling a rule without deleting it
- **WHEN** a rule's `enabled` field is updated to `false`
- **THEN** the rule remains in the table but is excluded from the compiled pipeline on the next analysis

#### Scenario: Deleting a rule
- **WHEN** `DELETE /entity-rules/{id}` is called
- **THEN** the rule no longer appears in subsequent list calls

### Requirement: Existing labels are discoverable for reuse
The system SHALL expose the distinct set of labels currently in use, so the admin UI can offer them as suggestions without hardcoding a taxonomy.

#### Scenario: Label suggestions
- **WHEN** `GET /entity-rules/labels` is called
- **THEN** it returns the distinct `label` values currently present across all rules

### Requirement: Rules are managed through a dedicated admin page
The UI SHALL provide an Entity Rules page (opened as a MainWindow view, alongside Prompts and Katalog) listing every rule with its label, pattern preview, pattern_id, and enabled state, with actions to create, edit, toggle, and delete a rule.

#### Scenario: Editing a pattern
- **WHEN** the user opens a rule's edit dialog and changes its pattern JSON
- **THEN** the client validates the JSON is well-formed before submitting, and the server's spaCy validation error (if any) is shown inline on failure
