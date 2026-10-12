"""PDF forms (Formblätter): detection, identification, role, and extraction.

`identify_formblatt` reads the Formblatt number from the printed footer;
`detect_form_kind` decides from the bytes (and that id) whether a PDF is a form (XFA,
AcroForm with enough fields, or a flattened form with a known id); `classify_form_role`
decides who fills it; `extract_form` turns it into source lines on one shared contract
(`forms/model.py`) plus structured form fields.
"""
