from __future__ import annotations

from uuid import uuid4

from shared.services.ingestion.forms.xfa import extract_xfa_packets

# Trimmed from FB 312-B: master-page title, the Adobe button bar, and two sections.
TEMPLATE = b"""<template xmlns="http://www.xfa.org/schema/xfa-template/3.3/">
<subform name="topmostSubform">
  <pageSet><pageArea><draw name="T0"><value><text>Formblatt 312-B Angebotsaufforderung</text></value></draw></pageArea></pageSet>
  <subform name="btn">
    <field name="Schaltflaeche1"><ui><button/></ui></field>
    <draw><value><text>Den aktuellen Adobe Reader koennen Sie hier downloaden.</text></value></draw>
  </subform>
  <subform name="Page1">
    <subform name="Kopf">
      <field name="VS_Logo_L__SB_"><ui><imageEdit/></ui></field>
      <draw name="AngabenVergabestelle"><value><text>Vergabestelle:</text></value></draw>
      <subform name="Kopf_VS">
        <field name="VS_NAME1_L__SB_"><ui><textEdit/></ui>
          <assist><toolTip>Name Vergabestelle</toolTip></assist></field>
        <field name="VS_FAX_L__SB_"><ui><textEdit/></ui>
          <assist><toolTip>Telefax</toolTip></assist></field>
      </subform>
      <exclGroup name="Optionsfeldliste_L__SB_">
        <field name="VE_OV_L__SB_"><ui><checkButton/></ui>
          <caption><value><text>Offenes Verfahren</text></value></caption>
          <items><text>1</text></items></field>
        <field name="VE_NOV_L__SB_"><ui><checkButton/></ui>
          <caption><value><text>Nicht offenes Verfahren</text></value></caption>
          <items><text>2</text></items></field>
      </exclGroup>
      <field name="VE_EINREICH_DAT_L__SB_"><ui><dateTimeEdit/></ui>
        <caption><value><text>Einreichungsdatum:</text></value></caption></field>
      <field name="Versteckt_L__SB_" presence="hidden"><ui><textEdit/></ui></field>
      <field name="ID_Formular"><ui><textEdit/></ui></field>
      <field name="Drucken"><ui><button/></ui></field>
    </subform>
    <subform name="Leer"><draw><value><text/></value></draw></subform>
    <subform name="Anlagen">
      <draw name="Text84"><value><exData contentType="text/html">
        <body xmlns="http://www.w3.org/1999/xhtml"><p>Hinweis:</p><p>Die   PDF-Formblaetter
        sind optimiert.</p></body></exData></value></draw>
      <subform>
        <field name="VE_ANL_BWB_L__SB_"><ui><checkButton/></ui>
          <caption><value><text>Teilnahmebedingungen</text></value></caption>
          <items><text>JA</text><text>Off</text></items></field>
        <field name="VE_ANL_GEW_L__SB_"><ui><checkButton/></ui>
          <caption><value><text>Gewichtung</text></value></caption>
          <items><text>JA</text><text>Off</text></items></field>
      </subform>
    </subform>
  </subform>
</subform>
</template>"""

DATASETS = b"""<xfa:datasets xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/">
<xfa:data><topmostSubform><Page1>
  <Kopf>
    <VS_Logo_L__SB_>/9j/4AAQ</VS_Logo_L__SB_>
    <Kopf_VS><VS_NAME1_L__SB_>Wasserstrassen-Neubauamt Berlin</VS_NAME1_L__SB_><VS_FAX_L__SB_/></Kopf_VS>
    <Optionsfeldliste_L__SB_>1</Optionsfeldliste_L__SB_>
    <VE_EINREICH_DAT_L__SB_>2026-10-15</VE_EINREICH_DAT_L__SB_>
    <Versteckt_L__SB_>geheim</Versteckt_L__SB_>
    <ID_Formular>312</ID_Formular>
  </Kopf>
  <Anlagen>
    <VE_ANL_BWB_L__SB_>JA</VE_ANL_BWB_L__SB_>
    <VE_ANL_GEW_L__SB_>Off</VE_ANL_GEW_L__SB_>
  </Anlagen>
</Page1></topmostSubform></xfa:data>
</xfa:datasets>"""


def test_lines_follow_template_order_with_section_headings() -> None:
    extraction = extract_xfa_packets(TEMPLATE, DATASETS, uuid4())

    assert [line.line_text for line in extraction.lines] == [
        "Formblatt 312-B Angebotsaufforderung",
        "## Kopf",
        "Vergabestelle:",
        "Name Vergabestelle: Wasserstrassen-Neubauamt Berlin",
        "Optionsfeldliste_L__SB_: Offenes Verfahren",
        "Einreichungsdatum: 2026-10-15",
        "## Anlagen",
        "Hinweis:",
        "Die PDF-Formblaetter sind optimiert.",
        "Teilnahmebedingungen: ja",
        "Gewichtung: nein",
    ]
    assert {line.page for line in extraction.lines} == {1}
    assert {line.bbox for line in extraction.lines} == {(0.0, 0.0, 0.0, 0.0)}
    assert [line.line_id for line in extraction.lines] == list(range(11))


def test_fields_carry_section_label_and_value() -> None:
    extraction = extract_xfa_packets(TEMPLATE, DATASETS, uuid4())

    assert [(f.section, f.name, f.label, f.value) for f in extraction.fields] == [
        ("Kopf", "VS_NAME1_L__SB_", "Name Vergabestelle", "Wasserstrassen-Neubauamt Berlin"),
        ("Kopf", "Optionsfeldliste_L__SB_", None, "Offenes Verfahren"),
        ("Kopf", "VE_EINREICH_DAT_L__SB_", "Einreichungsdatum", "2026-10-15"),
        ("Anlagen", "VE_ANL_BWB_L__SB_", "Teilnahmebedingungen", "ja"),
        ("Anlagen", "VE_ANL_GEW_L__SB_", "Gewichtung", "nein"),
    ]
    assert [f.field_order for f in extraction.fields] == list(range(5))
    assert {f.page for f in extraction.fields} == {1}


def test_without_datasets_only_template_defaults_remain() -> None:
    extraction = extract_xfa_packets(TEMPLATE, None, uuid4())

    assert [(f.name, f.value) for f in extraction.fields] == [
        ("VE_ANL_BWB_L__SB_", "nein"),
        ("VE_ANL_GEW_L__SB_", "nein"),
    ]
