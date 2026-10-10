// Edit the project header: Maßnahme (name), Maßnahmenummer, Vergabenummer, Bauleistung,
// Vergabestelle, Baustelle and description. Mounted only while open, so the form state
// initialises from the current project each time. Empty optional inputs are sent as
// null so a field can be cleared.

import { useState } from 'react';
import { useUpdateProject } from '../../api/projects';
import type { ProjectRead, ProjectUpdate } from '../../types/generated';
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogTitle,
} from '../../components/ui/dialog';
import { Field, Fieldset, Label } from '../../components/ui/fieldset';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import { Button } from '../../components/ui/button';

type TextField = Exclude<keyof ProjectUpdate, 'project_description'>;

const TEXT_FIELDS: { key: TextField; label: string }[] = [
  { key: 'project_name', label: 'Maßnahme (Project Name)' },
  { key: 'massnahmenummer', label: 'Maßnahmenummer' },
  { key: 'vergabe_id', label: 'Vergabenummer' },
  { key: 'bauleistung', label: 'Bauleistung' },
  { key: 'vergabestelle', label: 'Vergabestelle' },
  { key: 'location', label: 'Baustelle' },
];

function nullIfBlank(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

export function EditProjectDialog({
  project,
  onClose,
}: {
  project: ProjectRead;
  onClose: () => void;
}) {
  const update = useUpdateProject(project.project_uuid);
  const [values, setValues] = useState<Record<TextField, string>>({
    project_name: project.project_name,
    massnahmenummer: project.massnahmenummer ?? '',
    vergabe_id: project.vergabe_id ?? '',
    bauleistung: project.bauleistung ?? '',
    vergabestelle: project.vergabestelle ?? '',
    location: project.location ?? '',
  });
  const [description, setDescription] = useState(project.project_description ?? '');
  const [error, setError] = useState<string | null>(null);

  const canSubmit = values.project_name.trim().length > 0 && !update.isPending;

  const close = () => {
    if (update.isPending) return;
    onClose();
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await update.mutateAsync({
        project_name: values.project_name.trim(),
        massnahmenummer: nullIfBlank(values.massnahmenummer),
        vergabe_id: nullIfBlank(values.vergabe_id),
        bauleistung: nullIfBlank(values.bauleistung),
        vergabestelle: nullIfBlank(values.vergabestelle),
        location: nullIfBlank(values.location),
        project_description: nullIfBlank(description),
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <Dialog open onClose={close} size="2xl">
      <form onSubmit={submit}>
        <DialogTitle>Edit project</DialogTitle>
        <DialogBody>
          <Fieldset>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {TEXT_FIELDS.map(({ key, label }) => (
                <Field key={key}>
                  <Label>{label}</Label>
                  <Input
                    value={values[key]}
                    onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))}
                    required={key === 'project_name'}
                  />
                </Field>
              ))}
            </div>
            <Field className="mt-4">
              <Label>Description</Label>
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
              />
            </Field>
          </Fieldset>
          {error && <div className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</div>}
        </DialogBody>
        <DialogActions>
          <Button plain type="button" onClick={close}>
            Cancel
          </Button>
          <Button type="submit" disabled={!canSubmit}>
            {update.isPending ? 'Saving…' : 'Save'}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
