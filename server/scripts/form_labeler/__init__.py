"""Streamlit ground-truth labeler for Formblätter.

Shows a form page as an image next to the pipeline's own extracted lines, lets the
labeler mark each line as no box / unchecked / checked, and collects per tender a list
of fact questions with gold answers. Labels are JSON files under `eval/forms/`; nothing
here touches Postgres, Elasticsearch or MinIO.

    uv run --group tools streamlit run server/scripts/form_labeler/app.py
"""
