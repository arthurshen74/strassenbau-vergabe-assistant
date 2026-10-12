"""Streamlit entry of the Formblatt labeler.

Sidebar: tender, form list, page navigation. Main: the page image next to one row per
extracted line with a tri-state radio (no box / unchecked / checked), and a facts tab
with the per-tender fact editor. Reads the corpus at `$FORM_LABELER_CORPUS` (default
`server/training`) and writes `eval/forms/labels/` and `eval/forms/facts/`.

    uv run --group tools streamlit run server/scripts/form_labeler/app.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

SERVER_DIR = Path(__file__).resolve().parents[2]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402

from scripts.form_labeler.corpus import (  # noqa: E402
    FormPdf,
    Tender,
    list_forms,
    list_tenders,
    page_lines,
)
from scripts.form_labeler.facts import (  # noqa: E402
    COL_GOLD,
    COL_KIND,
    COL_PAGE,
    COL_PDF,
    COLUMNS,
    default_facts,
    facts_to_rows,
    rows_to_facts,
)
from scripts.form_labeler.pages import render_page  # noqa: E402
from scripts.form_labeler.proposals import MARGINAL_TOKEN, propose  # noqa: E402
from scripts.form_labeler.store import (  # noqa: E402
    FactFile,
    FactKind,
    FormLabels,
    LineLabel,
    LineState,
    PdfKind,
    facts_path,
    labels_path,
    load_facts,
    load_labels,
    save_facts,
    save_labels,
)
from shared.models.source_line import NewSourceLine  # noqa: E402
from shared.services.ingestion.forms.detect import FormKind  # noqa: E402
from shared.services.ingestion.forms.extraction import extract_form  # noqa: E402

REPO_ROOT = SERVER_DIR.parent
ENV_CORPUS = "FORM_LABELER_CORPUS"
DEFAULT_CORPUS = REPO_ROOT / "server" / "training"
EVAL_ROOT = REPO_ROOT / "eval" / "forms"

PAGE_WIDTH_PX = 640
LIST_HEIGHT_PX = 420

KEY_TENDER = "tender"
KEY_FORM_INDEX = "form_index"
KEY_PAGE = "page"
KEY_PROPOSED = "proposed"
KEY_ROWS = "form-rows"
ROW_KEY_PREFIX = "form-row-"
ROW_CLASS_PREFIX = f"st-key-{ROW_KEY_PREFIX}"
LINE_KEY_PREFIX = "line"

SYMBOLS = {LineState.NONE: "–", LineState.UNCHECKED: "☐", LineState.CHECKED: "☒"}
ICON_DONE = ":green[:material/check_circle:]"
ICON_OPEN = ":gray[:material/radio_button_unchecked:]"
PROPOSAL_CAPTION = ":orange[Vorschlag]"

CSS = """
<style>
.block-container {padding-top: 2.5rem; padding-bottom: 0.5rem;}
section[data-testid="stSidebar"] {width: 440px !important;}
.st-key-form-rows button {
    justify-content: flex-start; border: none; border-radius: 0; min-height: 0;
    padding: 0.15rem 0.5rem 0.15rem 0.75rem; color: inherit;
}
.st-key-form-rows button > div {width: 100%; justify-content: flex-start;}
.st-key-form-rows button p {text-align: left; font-size: 0.8rem;}
.st-key-form-rows button[kind="primary"] {
    background-color: rgba(28, 131, 225, 0.18);
    box-shadow: inset 4px 0 0 rgb(28, 131, 225); font-weight: 600;
}
div[data-testid="stRadio"] > div {gap: 0.2rem;}
div[data-testid="stRadio"] label {padding: 0 0.3rem; margin: 0;}
.line-text {font-family: monospace; font-size: 0.78rem; white-space: pre-wrap;
    margin: 0; padding-top: 0.25rem;}
.line-dim {color: #999;}
</style>
"""

SCROLL_JS = """
<script>
(function () {
    let tries = 0;
    function go() {
        const row = window.parent.document.querySelector(".%s");
        if (row) { row.scrollIntoView({block: "nearest"}); return; }
        if (tries++ < 20) { setTimeout(go, 50); }
    }
    go();
})();
</script>
"""


def main() -> None:
    st.set_page_config(page_title="Formblatt Labeler", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    corpus = Path(os.environ.get(ENV_CORPUS, DEFAULT_CORPUS))
    tenders = list_tenders(corpus) if corpus.is_dir() else []
    if not tenders:
        st.info(f"Keine Tender unter `{corpus}` gefunden (`{ENV_CORPUS}` setzen).")
        return
    st.session_state.setdefault(KEY_PROPOSED, set())

    tender, forms, labels = _sidebar(tenders)
    if not forms:
        st.info("Dieser Tender enthält keine Formblätter.")
        return
    form = forms[st.session_state[KEY_FORM_INDEX]]
    page = st.session_state[KEY_PAGE]
    boxes_tab, facts_tab = st.tabs(["Kästchen", "Fakten"])
    with boxes_tab:
        _boxes_pane(form, page, forms, labels)
    with facts_tab:
        _facts_pane(tender, forms)


def _sidebar(
    tenders: list[Tender],
) -> tuple[Tender, list[FormPdf], dict[str, FormLabels]]:
    with st.sidebar:
        names = [t.name for t in tenders]
        name = st.selectbox("Tender", names, key=KEY_TENDER, on_change=_reset_position)
        tender = tenders[names.index(name)]
        forms = _forms(str(tender.path), tender.name)
        labels = {
            f.stem: _load(labels_path(EVAL_ROOT, tender.name, f.stem)) for f in forms
        }
        labels = {stem: lab for stem, lab in labels.items() if lab is not None}
        st.session_state.setdefault(KEY_FORM_INDEX, 0)
        st.session_state.setdefault(KEY_PAGE, 1)
        if not forms:
            return tender, forms, labels
        st.session_state[KEY_FORM_INDEX] = min(
            st.session_state[KEY_FORM_INDEX], len(forms) - 1
        )
        _status_line(tender, forms, labels)
        _form_list(forms, labels)
        form = forms[st.session_state[KEY_FORM_INDEX]]
        _page_nav(form, labels.get(form.stem))
    return tender, forms, labels


def _status_line(
    tender: Tender, forms: list[FormPdf], labels: dict[str, FormLabels]
) -> None:
    total = sum(f.pages for f in forms)
    done = sum(len(labels[f.stem].labelled_pages) for f in forms if f.stem in labels)
    facts = _facts(tender)
    gold = sum(1 for fact in facts.facts if fact.is_labelled)
    st.caption(
        f"Seiten bestätigt {done} / {total} · "
        f"Fakten mit Gold {gold} / {len(facts.facts)}"
    )


def _form_list(forms: list[FormPdf], labels: dict[str, FormLabels]) -> None:
    index = st.session_state[KEY_FORM_INDEX]
    with st.container(height=LIST_HEIGHT_PX, gap=None, key=KEY_ROWS):
        for i, form in enumerate(forms):
            if form.is_bieter and i == next(
                j for j, f in enumerate(forms) if f.is_bieter
            ):
                st.caption("Bieter-Formblätter")
            _form_button(i, form, labels.get(form.stem), i == index)
        components.html(SCROLL_JS % f"{ROW_CLASS_PREFIX}{index}", height=0)


def _form_button(
    i: int, form: FormPdf, labels: FormLabels | None, selected: bool
) -> None:
    done = labels is not None and len(labels.labelled_pages) >= form.pages
    icon = ICON_DONE if done else ICON_OPEN
    title = form.form_id or form.role.value
    label = f"{icon} {title} · {form.kind.value} · {form.pages} S."
    if st.button(
        f"{label}  \n{Path(form.rel).name}",
        key=f"{ROW_KEY_PREFIX}{i}",
        type="primary" if selected else "secondary",
        width="stretch",
    ):
        st.session_state[KEY_FORM_INDEX] = i
        st.session_state[KEY_PAGE] = _next_unconfirmed(form, labels, 0) or 1
        st.rerun()


def _page_nav(form: FormPdf, labels: FormLabels | None) -> None:
    page = min(max(st.session_state[KEY_PAGE], 1), max(form.pages, 1))
    back, label, nxt = st.columns([1, 2, 1])
    if back.button("‹", width="stretch", disabled=page <= 1):
        page -= 1
    if nxt.button("›", width="stretch", disabled=page >= form.pages):
        page += 1
    confirmed = labels is not None and page in labels.labelled_pages
    label.markdown(
        f"<div style='text-align:center;padding-top:0.4rem'>Seite {page} / {form.pages}"
        f"{' ✓' if confirmed else ''}</div>",
        unsafe_allow_html=True,
    )
    if st.button("nächste unbestätigte Seite", width="stretch"):
        page = _next_unconfirmed(form, labels, page) or page
    st.session_state[KEY_PAGE] = page
    st.caption(f"{form.rel}")


def _boxes_pane(
    form: FormPdf, page: int, forms: list[FormPdf], labels: dict[str, FormLabels]
) -> None:
    left, right = st.columns([1, 1.1])
    with left:
        try:
            st.image(str(render_page(form.path, page, EVAL_ROOT)), width=PAGE_WIDTH_PX)
        except Exception as exc:  # pdf2image raises its own hierarchy
            st.error(f"Seite nicht lesbar: {exc}")
    with right:
        if form.kind is PdfKind.XFA:
            _xfa_pane(form, page, forms, labels)
        else:
            _lines_pane(form, page, forms, labels)


def _xfa_pane(
    form: FormPdf, page: int, forms: list[FormPdf], labels: dict[str, FormLabels]
) -> None:
    st.warning(
        "XFA-Formular: pdftotext liefert keine Seitenzeilen, Kästchen werden hier "
        "nicht gelabelt. Zur Referenz die Felder der Pipeline (extract_form):"
    )
    st.button(
        "Seite bestätigen",
        type="primary",
        on_click=_confirm,
        args=(form, page, [], [], forms, labels),
    )
    with st.container(height=700):
        for text in _xfa_lines(str(form.path)):
            st.markdown(
                f"<p class='line-text'>{_escape(text)}</p>", unsafe_allow_html=True
            )


def _lines_pane(
    form: FormPdf, page: int, forms: list[FormPdf], labels: dict[str, FormLabels]
) -> None:
    lines = _lines(str(form.path), page)
    existing = labels.get(form.stem)
    confirmed = existing is not None and page in existing.labelled_pages
    proposals = _proposals(str(form.path), page) if not confirmed else {}
    keys = [f"{LINE_KEY_PREFIX}:{form.stem}:{page}:{i}" for i in range(len(lines))]
    proposed: set[str] = st.session_state[KEY_PROPOSED]
    for i, (line, key) in enumerate(zip(lines, keys)):
        if key in st.session_state:
            continue
        state = _labelled_state(existing, line)
        if state is None and i in proposals:
            state = proposals[i]
            proposed.add(key)
        st.session_state[key] = state or LineState.NONE

    confirm, discard, redo = st.columns([1.2, 1, 1])
    confirm.button(
        "Seite bestätigen",
        type="primary",
        width="stretch",
        on_click=_confirm,
        args=(form, page, lines, keys, forms, labels),
    )
    discard.button(
        "Vorschläge verwerfen", width="stretch", on_click=_discard, args=(keys,)
    )
    redo.button(
        "Vorschläge neu", width="stretch", on_click=_repropose, args=(keys, proposals)
    )
    if confirmed:
        st.caption("Seite bestätigt. Änderungen erneut bestätigen.")
    with st.container(height=700):
        for line, key in zip(lines, keys):
            text_col, radio_col = st.columns([3, 1.3])
            dim = " line-dim" if MARGINAL_TOKEN.match(line.line_text) else ""
            text_col.markdown(
                f"<p class='line-text{dim}'>{_escape(line.line_text)}</p>",
                unsafe_allow_html=True,
            )
            radio_col.radio(
                "Status",
                list(LineState),
                format_func=SYMBOLS.__getitem__,
                horizontal=True,
                label_visibility="collapsed",
                key=key,
            )
            if key in proposed and not confirmed:
                radio_col.caption(PROPOSAL_CAPTION)


def _facts_pane(tender: Tender, forms: list[FormPdf]) -> None:
    facts = _facts(tender)
    rels = [f.rel for f in forms]
    frame = pd.DataFrame(facts_to_rows(facts), columns=list(COLUMNS))
    edited = st.data_editor(
        frame,
        key=f"facts:{tender.name}",
        num_rows="dynamic",
        width="stretch",
        column_config={
            COL_KIND: st.column_config.SelectboxColumn(
                options=[k.value for k in FactKind], required=True
            ),
            COL_PDF: st.column_config.SelectboxColumn(options=rels),
            COL_PAGE: st.column_config.NumberColumn(min_value=1, step=1),
            COL_GOLD: st.column_config.TextColumn(
                help="Liste: Einträge mit `; ` trennen"
            ),
        },
    )
    if st.button("Speichern", type="primary"):
        save_facts(
            facts_path(EVAL_ROOT, tender.name),
            rows_to_facts(tender.name, edited.to_dict("records")),
        )
        st.success("Gespeichert.")
        st.rerun()
    xfa_forms = [f for f in forms if f.kind is PdfKind.XFA and not f.is_bieter]
    for form in xfa_forms:
        with st.expander(f"Felder {form.form_id or form.rel} (XFA)"):
            st.code("\n".join(_xfa_lines(str(form.path))), language=None)


def _confirm(
    form: FormPdf,
    page: int,
    lines: list[NewSourceLine],
    keys: list[str],
    forms: list[FormPdf],
    labels: dict[str, FormLabels],
) -> None:
    existing = labels.get(form.stem) or FormLabels(
        tender=form.tender, pdf=form.rel, form_id=form.form_id, kind=form.kind
    )
    page_labels = [
        LineLabel(
            page=page, bbox=line.bbox, text=line.line_text, state=st.session_state[key]
        )
        for line, key in zip(lines, keys)
    ]
    updated = existing.with_page(page, page_labels)
    save_labels(labels_path(EVAL_ROOT, form.tender, form.stem), updated)
    labels[form.stem] = updated
    st.session_state[KEY_PROPOSED].difference_update(keys)
    next_page = _next_unconfirmed(form, updated, page)
    if next_page is not None:
        st.session_state[KEY_PAGE] = next_page
        return
    index = st.session_state[KEY_FORM_INDEX]
    for step in range(1, len(forms)):
        candidate = forms[(index + step) % len(forms)]
        first = _next_unconfirmed(candidate, labels.get(candidate.stem), 0)
        if first is not None:
            st.session_state[KEY_FORM_INDEX] = (index + step) % len(forms)
            st.session_state[KEY_PAGE] = first
            return


def _discard(keys: list[str]) -> None:
    for key in keys:
        st.session_state[key] = LineState.NONE
    st.session_state[KEY_PROPOSED].difference_update(keys)


def _repropose(keys: list[str], proposals: dict[int, LineState]) -> None:
    for i, key in enumerate(keys):
        st.session_state[key] = proposals.get(i, LineState.NONE)
        if i in proposals:
            st.session_state[KEY_PROPOSED].add(key)


def _reset_position() -> None:
    st.session_state[KEY_FORM_INDEX] = 0
    st.session_state[KEY_PAGE] = 1


def _next_unconfirmed(
    form: FormPdf, labels: FormLabels | None, after: int
) -> int | None:
    """The first page after `after` (wrapping) that is not confirmed, or None."""
    confirmed = set(labels.labelled_pages) if labels else set()
    for step in range(1, form.pages + 1):
        page = (after + step - 1) % form.pages + 1
        if page not in confirmed:
            return page
    return None


def _labelled_state(labels: FormLabels | None, line: NewSourceLine) -> LineState | None:
    if labels is None:
        return None
    for label in labels.page_lines(line.page):
        if label.text == line.line_text and label.bbox == line.bbox:
            return label.state
    return LineState.NONE if line.page in labels.labelled_pages else None


def _facts(tender: Tender) -> FactFile:
    path = facts_path(EVAL_ROOT, tender.name)
    return load_facts(path) if path.is_file() else default_facts(tender.name)


def _load(path: Path) -> FormLabels | None:
    return load_labels(path) if path.is_file() else None


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@st.cache_data(show_spinner="Formblätter werden gesucht ...")
def _forms(path: str, name: str) -> list[FormPdf]:
    return list_forms(Tender(name=name, path=Path(path)))


@st.cache_data(show_spinner=False)
def _lines(path: str, page: int) -> list[NewSourceLine]:
    return page_lines(Path(path).read_bytes(), page)


@st.cache_data(show_spinner=False)
def _proposals(path: str, page: int) -> dict[int, LineState]:
    return propose(Path(path), page, _lines(path, page))


@st.cache_data(show_spinner=False)
def _xfa_lines(path: str) -> list[str]:
    extraction = extract_form(Path(path).read_bytes(), uuid4(), FormKind.XFA)
    return [line.line_text for line in extraction.lines]


main()
