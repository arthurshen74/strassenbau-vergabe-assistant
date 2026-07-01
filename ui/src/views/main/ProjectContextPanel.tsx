// Project-level context panel: view, resolve and override the project's global variables
// (Baustelle, Deponie, strip dimensions, Fräsgutklasse) outside a calculation, with version
// history. The pre-Gate-A review (InterruptPanel) is the primary editor; this is the optional
// standalone surface (PROJECT_CONTEXT_PLAN §12.2).

import { useState } from "react";
import {
  useClearProjectContext,
  useProjectContext,
  useProjectContextHistory,
  useResolveProjectContext,
  useUpdateProjectContext,
} from "../../api/project-context";
import type {
  ProjectContextRead,
  ProjectContextUpdate,
} from "../../types/generated";
import { Heading } from "../../components/ui/heading";
import { Text } from "../../components/ui/text";
import { Button } from "../../components/ui/button";
import { Field, Label } from "../../components/ui/fieldset";
import { Input } from "../../components/ui/input";
import { LoadingState } from "../../components/feedback/LoadingState";
import { ErrorState } from "../../components/feedback/ErrorState";

// Location geocoding status, matching the backend ContextStatus values.
const STATUS_OK = "aufgeloest";
const STATUS_UNSICHER = "unsicher";
const STATUS_FEHLT = "fehlgeschlagen";

function StatusHint({ status }: { status: string | null | undefined }) {
  if (status === STATUS_OK) {
    return <span className="ml-2 text-zinc-500">geokodiert</span>;
  }
  if (status === STATUS_UNSICHER) {
    return (
      <span className="ml-2 text-amber-700 dark:text-amber-400">
        unsicher — bitte prüfen
      </span>
    );
  }
  if (status === STATUS_FEHLT) {
    return (
      <span className="ml-2 text-amber-700 dark:text-amber-400">
        nicht geokodiert — bitte prüfen
      </span>
    );
  }
  return null;
}

function ContextForm({
  projectUuid,
  initial,
}: {
  projectUuid: string;
  initial: ProjectContextRead;
}) {
  const update = useUpdateProjectContext(projectUuid);
  const [baustelle, setBaustelle] = useState(initial.baustelle_location ?? "");
  const [deponie, setDeponie] = useState(initial.deponie_location ?? "");
  const [length, setLength] = useState(initial.strip_length_m ?? "");
  const [width, setWidth] = useState(initial.strip_width_m ?? "");
  const [fraesgut, setFraesgut] = useState(initial.fraesgut_klasse ?? "");

  // Only send fields the user actually changed; each becomes a new version.
  function changedFields(): ProjectContextUpdate {
    const body: ProjectContextUpdate = {};
    if (baustelle !== (initial.baustelle_location ?? "")) body.baustelle_location = baustelle;
    if (deponie !== (initial.deponie_location ?? "")) body.deponie_location = deponie;
    if (length !== (initial.strip_length_m ?? "")) body.strip_length_m = length;
    if (width !== (initial.strip_width_m ?? "")) body.strip_width_m = width;
    if (fraesgut !== (initial.fraesgut_klasse ?? "")) body.fraesgut_klasse = fraesgut;
    return body;
  }

  const dirty = Object.keys(changedFields()).length > 0;

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (dirty) update.mutate(changedFields());
      }}
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field>
          <Label>
            Baustelle (Standort)
            <StatusHint status={initial.baustelle_status} />
          </Label>
          <Input
            value={baustelle}
            placeholder="Adresse, Ort oder Streckenabschnitt"
            onChange={(e) => setBaustelle(e.target.value)}
          />
        </Field>
        <Field>
          <Label>
            Deponie / Entsorgung
            <StatusHint status={initial.deponie_status} />
          </Label>
          <Input
            value={deponie}
            placeholder="Adresse oder Ort der Deponie"
            onChange={(e) => setDeponie(e.target.value)}
          />
        </Field>
        <Field>
          <Label>Streckenlänge (m)</Label>
          <Input
            value={length}
            inputMode="decimal"
            onChange={(e) => setLength(e.target.value)}
          />
        </Field>
        <Field>
          <Label>Streckenbreite (m)</Label>
          <Input
            value={width}
            inputMode="decimal"
            onChange={(e) => setWidth(e.target.value)}
          />
        </Field>
        <Field>
          <Label>Fräsgutklasse</Label>
          <Input
            value={fraesgut}
            inputMode="numeric"
            onChange={(e) => setFraesgut(e.target.value)}
          />
        </Field>
        <Field>
          <Label>Entfernung zur Deponie (km, berechnet)</Label>
          <Input value={initial.entfernung_deponie_km ?? "—"} disabled readOnly />
        </Field>
      </div>
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={!dirty || update.isPending}>
          {update.isPending ? "Speichert…" : "Überschreiben & speichern"}
        </Button>
        {update.isError && (
          <Text className="text-sm text-red-600 dark:text-red-400">
            {(update.error as Error).message}
          </Text>
        )}
      </div>
    </form>
  );
}

function VersionHistory({ projectUuid }: { projectUuid: string }) {
  const history = useProjectContextHistory(projectUuid);
  const [open, setOpen] = useState(false);
  if (!history.data || history.data.length === 0) return null;
  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        className="self-start text-sm text-indigo-600 hover:underline dark:text-indigo-400"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "Versionsverlauf ausblenden" : "Versionsverlauf anzeigen"}
      </button>
      {open && (
        <div className="flex flex-col gap-3">
          {history.data.map((entry) => (
            <div key={entry.variable_name} className="flex flex-col gap-1">
              <Text className="text-xs font-medium text-zinc-700 dark:text-zinc-300">
                {entry.variable_name}
              </Text>
              <ul className="flex flex-col gap-0.5">
                {entry.versionen.map((v) => (
                  <li
                    key={v.version}
                    className="text-xs text-zinc-500 dark:text-zinc-400"
                  >
                    v{v.version} · {v.wert} · {v.quelle}
                    {v.benutzer ? ` · ${v.benutzer}` : ""}
                    {v.ist_aktuell ? " · aktuell" : ""}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function ProjectContextPanel({ projectUuid }: { projectUuid: string }) {
  const context = useProjectContext(projectUuid);
  const resolve = useResolveProjectContext(projectUuid);
  const clear = useClearProjectContext(projectUuid);

  if (context.isPending) return <LoadingState label="Lade Projektkontext…" />;
  if (context.isError) {
    return (
      <ErrorState
        message={(context.error as Error).message}
        onRetry={() => context.refetch()}
      />
    );
  }
  const data = context.data;
  // Key the form by the loaded values so a successful save (which refetches) re-seeds the inputs.
  const formKey = [
    data.baustelle_location,
    data.deponie_location,
    data.strip_length_m,
    data.strip_width_m,
    data.fraesgut_klasse,
  ].join("|");

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <Heading level={5}>Projektkontext (globale Variablen)</Heading>
        <div className="flex gap-2">
          {data.vorhanden && (
            <Button
              outline
              disabled={clear.isPending || resolve.isPending}
              onClick={() => {
                if (
                  window.confirm(
                    "Alle gespeicherten Projektkontext-Werte löschen? Die nächste Ermittlung startet neu (inkl. Geokodierung).",
                  )
                ) {
                  clear.mutate();
                }
              }}
            >
              {clear.isPending ? "Setzt zurück…" : "Zurücksetzen"}
            </Button>
          )}
          <Button outline disabled={resolve.isPending} onClick={() => resolve.mutate()}>
            {resolve.isPending ? "Ermittelt…" : "Fehlende automatisch ermitteln"}
          </Button>
        </div>
      </div>
      {clear.isError && (
        <Text className="text-sm text-red-600 dark:text-red-400">
          {(clear.error as Error).message}
        </Text>
      )}
      {!data.vorhanden && (
        <Text className="text-sm text-zinc-500">
          Noch keine Werte. „Fehlende automatisch ermitteln“ startet die Recherche aus den
          Vergabeunterlagen, oder Werte direkt eintragen.
        </Text>
      )}
      {resolve.isError && (
        <Text className="text-sm text-red-600 dark:text-red-400">
          {(resolve.error as Error).message}
        </Text>
      )}
      <ContextForm key={formKey} projectUuid={projectUuid} initial={data} />
      <VersionHistory projectUuid={projectUuid} />
    </div>
  );
}
