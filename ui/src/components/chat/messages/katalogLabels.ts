// Display labels shared by the katalog draft renderers (KatalogEntwurfCard, KatalogEntwurfListe).

export const ENTITAET_LABEL: Record<string, string> = {
  baustoffe: 'Baustoff',
  maschinen: 'Maschine',
  lieferanten: 'Lieferant',
  preise: 'Preis',
  formeln: 'Formel',
  variablen: 'Variable',
  ausfuehrungsarten: 'Geräteklasse',
  betriebskategorien: 'Betriebskategorie',
  betriebsarten: 'Betriebsart',
  leistung_bauverfahren: 'Leistung → Bauverfahren',
  entwurf: 'Entwurf',
  bundle: 'Katalog-Bundle',
};

export const ZUSTAND_LABEL: Record<string, string> = {
  aktiviert: 'Aktiviert.',
  verworfen: 'Verworfen.',
  geschlossen: 'Aktiviert, später überholt.',
};
