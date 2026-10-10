"""Fillable PDF forms (Formblätter): detection, role by filename, and field extraction.

`detect_form_kind` decides from the bytes whether a PDF is a form (XFA, or an AcroForm
with enough fields); `classify_form_role` decides from the filename who fills it;
`extract_form` turns it into source lines plus structured form fields.
"""
