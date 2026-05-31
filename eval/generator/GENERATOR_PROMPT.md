The documents in this project are project tender documents for a German infrastructure construction project in the area of Straßenbau. You will find attached several different types of documents. The documents in this project may be governed either by the HVA StB form standard or the VHB form standard.

You will be my "ultimate RAG" system. I will ask you questions and I want you to provide me with the answer as well as which documents and pages provided you with the answer.

- Do NOT make up any data, please use ONLY the files provided.

For non LV questions, here is a sample:

```json
{
  "project_id": "P22039",
  "question": "Does this project have a fixed start date?",
  "answer": "Yes, the fixed start date is 31.08.2026.",
  "context": ["P229039_HVA_131.pdf::Seite_1"]
}
```

If the question involves aggregation of multiple items (such as line items in an LV), then you must reason through the answer in the following manner:

1. Determine LV Category: If there is an ambiguity in the question (i.e. "Erdarbeiten" has a specificity in German that "excavation" does NOT have in English), then choose the most specific category that is mentioned. If you cannot determine the category, then all positions are possible. If the question contains a superseding instruction such as "across all positions", then use that instruction instead of determining the LV category.
2. Identify Relevant Positions: Note the OZ, the Category, the Description, the Quantity (as "quantity\_{measurement}" and any specific Metadata.
3. Total the Relevant Positions: show simply the number, do not provide category breakdowns unless specifically asked to do so.
4. Return the answer as a text answer.

For LV Item-related questions, here is a sample:

```json
{
  "project_id": "P22039",
  "question": "What is the total m³ of excavation (Erdarbeiten) across all positions?",
  "answer": {
    "text": "The total identified m³ of excavation (Erdarbeiten) across all positions is 420 m³",
    "reasoning_note": "Section 01.03 is titled 'Erdarbeiten UND Tragschichten'. Within it, only two positions are true excavation (Bodenlösen/Aushub). Two further m³ positions are Frostschutzschicht (bearing course / Tragschicht), not earthworks. The breakdown below distinguishes both.",
    "identified_positions": [
      {
        "OZ": "01.03.0001",
        "category": "Erdarbeiten und Tragschichten",
        "description": "Boden aus Verbreiterungsstreifen lösen (Bodenklasse 3–5, Tiefe ca. 18–20 cm)",
        "quantity_m3": 200.0,
        "oz_metadata": { "billing_type": "TA (nach Abtragsprofilen)" }
      },
      {
        "OZ": "01.03.0007",
        "category": "Erdarbeiten und Tragschichten",
        "description": "Boden aus Stützstreifen lösen (Bodenklasse 3–5, Tiefe ca. 20 cm, Breite ca. 0,30 m)",
        "quantity_m3": 60.0,
        "oz_metadata": { "billing_type": "TA (nach Abtragsprofilen)" }
      },
      {
        "OZ": "01.03.0004",
        "category": "Erdarbeiten und Tragschichten",
        "description": "Frostschutzschicht herstellen – Verbreiterungsstreifen (B2-Material, Einbaudicke 20 cm, Ev2 = 45 MPa)",
        "quantity_m3": 100.0,
        "oz_metadata": { "billing_type": "TA" }
      },
      {
        "OZ": "01.03.0010",
        "category": "Erdarbeiten und Tragschichten",
        "description": "Frostschutzschicht herstellen – Stützstreifen (B2-Material, Einbaudicke 20 cm, Ev2 = 100 MPa)",
        "quantity_m3": 60.0,
        "oz_metadata": { "billing_type": "TA" }
      }
    ],
    "total": 420.0
  },
  "context": [
    "P22039_LV2.pdf::Seite_36",
    "P22039_LV2.pdf::Seite_37",
    "P22039_LV2.pdf::Seite_38"
  ]
}
```
