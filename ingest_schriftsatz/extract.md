You are reading paragraphs from a German Klageerwiderung (defendant's
answer) in a Kündigungsschutzklage. For each paragraph, extract every
atomic claim the paragraph makes — regardless of whether it is a
factual claim, a legal characterization, an evidentiary claim, or a
procedural position — and classify each.

FIELD SEMANTICS

- `assertion_text` (German): the atomic claim, lightly rephrased into
  canonical subject-verb-object form. Use the original German.
- `assertion_text_en` (English): a faithful translation of
  `assertion_text`. Konjunktiv I must be rendered with reported-speech
  framing ("the Defendant contends that ...", "allegedly",
  "purportedly") — never flatten into the indicative.
- `classification` — one of:
    - `factual` — a Tatsachenbehauptung; a verifiable fact about what
      happened, when, who did what.
    - `legal` — a legal characterization or conclusion (e.g. "this
      constitutes Vorsatz", "die Voraussetzungen des § 626 BGB sind
      erfüllt").
    - `evidentiary` — a claim about what an exhibit, document, or piece
      of evidence shows or proves.
    - `procedural` — a procedural reference or position (e.g. "die Klage
      ist unbegründet", "der Auflösungsantrag wird hilfsweise gestellt").
    - `rhetorical` — argumentative framing or emphasis without an
      independent verifiable claim.
  Pick the single best fit per assertion.
- `is_negative`: `true` iff the claim affirmatively states that
  something did NOT happen (e.g. "der Kläger erhielt keine Abmahnung").
  Plain assertions are `false`. Konjunktiv I reported-speech framing
  alone does not make a claim negative.

RULES

- Return an empty `assertions` array only if the paragraph contains no
  analyzable atomic claim (bare heading, pure cross-reference such as
  "siehe Anlage A 3", stand-alone connective phrase).
- Split a sentence that bundles multiple distinct claims into separate
  atomic assertions, one subject + verb + object/predicate each.
- Do not invent or infer claims beyond what the paragraph states.
