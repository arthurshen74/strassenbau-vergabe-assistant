// Routes a persisted function_call_output to its inline renderer by tool name.
// LV results and aggregates render in the thread; the context tools render only their verbose
// trace here (the sources move below the answer, see CitationsPanel). Dispatcher tools open the
// main window instead and render nothing here.

import type { MessageRead } from '../../../types/generated';
import { AggregateResultMessage } from './AggregateResultMessage';
import { EktResultMessage } from './EktResultMessage';
import { KatalogEntwurfCard } from './KatalogEntwurfCard';
import { KatalogEntwurfListe } from './KatalogEntwurfListe';
import { LvResultMessage } from './LvResultMessage';
import { MapResultMessage } from './MapResultMessage';
import { RetrievalTraceMessage } from './RetrievalTraceMessage';

// The catalog write tools (W1–W18) all emit a draft envelope the KatalogEntwurfCard renders;
// rezept_entwurf_speichern's envelope carries the sectioned recipe bundle.
const KATALOG_SCHREIB_WERKZEUGE = new Set<string>([
  'rezept_entwurf_speichern',
  'neue_formel',
  'aendere_formel',
  'neue_stammdaten_variable',
  'aendere_stammdaten_wert',
  'neue_kontext_variable',
  'neuer_baustoff',
  'aendere_baustoff',
  'neuer_lieferant',
  'aendere_lieferant',
  'neuer_preis',
  'neue_maschine',
  'aendere_maschine',
  'neue_ausfuehrungsart',
  'neue_betriebskategorie',
  'neue_betriebsart',
  'bauverfahren_zu_leistung',
  'entwurf_verwerfen',
]);

// The T33 draft listing renders as actionable rows (KatalogEntwurfListe).
const TOOL_LISTE_ENTWUERFE = 'liste_entwuerfe';

// Wire tool names, matching the names the project-chat agent emits (ProjectChatAgent tools).
export const TOOL_GET_PROJECT_CONTEXT = 'get_project_context';
export const TOOL_GET_LV_CONTEXT = 'get_lv_context';
export const TOOL_GET_LV_ALL = 'get_lv_all';
export const TOOL_GET_LV_SINGLE_ITEM = 'get_lv_single_item';
export const TOOL_GET_LV_GROUP_ITEMS = 'get_lv_group_items';
export const TOOL_AGGREGATE_LV_ITEMS = 'aggregate_lv_items';
export const TOOL_RENDER_MAP = 'render_map';
// Emitted by the EKT calculator run (CalculatorRunService), not a project-chat tool.
export const TOOL_EKT_RESULT = 'ekt_result';

export function ToolResultMessage({
  m,
  projectUuid,
}: {
  m: MessageRead;
  projectUuid?: string;
}) {
  if (!m.success) return null;
  if (m.tool_name && KATALOG_SCHREIB_WERKZEUGE.has(m.tool_name)) {
    return <KatalogEntwurfCard data={m.data ?? null} />;
  }
  if (m.tool_name === TOOL_LISTE_ENTWUERFE) {
    return <KatalogEntwurfListe data={m.data ?? null} />;
  }
  switch (m.tool_name) {
    case TOOL_GET_PROJECT_CONTEXT:
    case TOOL_GET_LV_CONTEXT:
      return <RetrievalTraceMessage data={m.data ?? null} />;
    case TOOL_GET_LV_SINGLE_ITEM:
    case TOOL_GET_LV_ALL:
    case TOOL_GET_LV_GROUP_ITEMS:
      return <LvResultMessage data={m.data ?? null} projectUuid={projectUuid} />;
    case TOOL_AGGREGATE_LV_ITEMS:
      return (
        <AggregateResultMessage data={m.data ?? null} projectUuid={projectUuid} />
      );
    case TOOL_RENDER_MAP:
      return <MapResultMessage data={m.data ?? null} projectUuid={projectUuid} />;
    case TOOL_EKT_RESULT:
      return <EktResultMessage data={m.data ?? null} />;
    default:
      return null;
  }
}
