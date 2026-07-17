# ner-analysis-dashboard Specification

## Purpose
The NER Analysis admin page: a per-category summary of flags, a filterable browsable flag list with full detail, resolve/re-categorize/re-run/delete actions, and sidebar reachability alongside Prompts and Entity Rules.

## Requirements

### Requirement: A summary dashboard aggregates flags by failure category
The NER Analysis page SHALL open with a summary header: total flag count and per-category counts (using the effective category — user override over LLM assignment), with AMBIGUITY visually highlighted in red, and open-vs-resolved visible per category.

#### Scenario: Reading the requirement-3 summary
- **WHEN** the user opens the NER Analysis page with 25 flags recorded
- **THEN** the header shows the total and a count per category (e.g. 9 register mismatch, 7 missing rules, 4 tokenization, 3 ambiguity in red), each with its resolved share

### Requirement: Flags are browsable with filters and full detail
The page SHALL list flags (span, label, kind, effective category, status, source, created date) filterable by kind, category, and status; selecting a flag SHALL show its full detail: sentence and source text, the flag-time entity snapshot, the user comment, the complete LLM analysis, its provenance (LLM model, prompt version, spaCy version, timestamp), and the suggested rule when present.

#### Scenario: Drilling into a flag
- **WHEN** the user selects a flag from the list
- **THEN** the detail view shows the sentence, comment, full analysis prose, provenance, and — if the LLM suggested a rule — the suggestion as copyable JSON with a pointer to the Entity Rules page

### Requirement: Flags can be resolved and re-categorized from the detail view
The detail view SHALL offer: resolve with a note (and reopen), category override, re-run analysis, and delete.

#### Scenario: Closing the loop
- **WHEN** the user adds the suggested rule in the Entity Rules page and returns to resolve the flag with a note
- **THEN** the flag shows RESOLVED with the note and the dashboard's resolved share updates

### Requirement: The page is reachable as a global admin view
The NER Analysis page SHALL be a MainWindow view opened from a sidebar command, alongside Prompts and Entity Rules.

#### Scenario: Opening from the sidebar
- **WHEN** the user clicks the NER Analysis sidebar command
- **THEN** the page opens in the main window with the dashboard and flag list
