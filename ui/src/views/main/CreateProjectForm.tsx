// Create-project form (step 1 of "Ingest New Project"). Only the Maßnahme (project name)
// is required; the other header fields can be filled in later. On success the parent
// navigates to the new project's Details, where documents are uploaded.

import { useState } from 'react';
import { ArrowLeftIcon } from '@heroicons/react/16/solid';
import type { ProjectRead } from '../../types/generated';
import { useCreateProject } from '../../api/projects';
import { Heading } from '../../components/ui/heading';
import { Button } from '../../components/ui/button';
import { Fieldset, Field, Label } from '../../components/ui/fieldset';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';

function nullIfBlank(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

export function CreateProjectForm({
  onBack,
  onCreated,
}: {
  onBack: () => void;
  onCreated: (p: ProjectRead) => void;
}) {
  const create = useCreateProject();
  const [projectName, setProjectName] = useState('');
  const [massnahmenummer, setMassnahmenummer] = useState('');
  const [vergabeId, setVergabeId] = useState('');
  const [bauleistung, setBauleistung] = useState('');
  const [vergabestelle, setVergabestelle] = useState('');
  const [location, setLocation] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState<string | null>(null);

  const canSubmit = projectName.trim() && !create.isPending;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const created = await create.mutateAsync({
        project_name: projectName.trim(),
        massnahmenummer: nullIfBlank(massnahmenummer),
        vergabe_id: nullIfBlank(vergabeId),
        bauleistung: nullIfBlank(bauleistung),
        vergabestelle: nullIfBlank(vergabestelle),
        location: nullIfBlank(location),
        project_description: nullIfBlank(description),
      });
      onCreated(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <form onSubmit={submit} className="flex max-w-2xl flex-col gap-4">
      <div className="flex items-center gap-2">
        <Button plain onClick={onBack} type="button" aria-label="Back">
          <ArrowLeftIcon />
        </Button>
        <Heading level={4}>Ingest New Project</Heading>
      </div>
      <Fieldset>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field>
            <Label>Maßnahme (Project Name)</Label>
            <Input value={projectName} onChange={(e) => setProjectName(e.target.value)} required />
          </Field>
          <Field>
            <Label>Maßnahmenummer</Label>
            <Input value={massnahmenummer} onChange={(e) => setMassnahmenummer(e.target.value)} />
          </Field>
          <Field>
            <Label>Vergabenummer</Label>
            <Input value={vergabeId} onChange={(e) => setVergabeId(e.target.value)} />
          </Field>
          <Field>
            <Label>Bauleistung</Label>
            <Input value={bauleistung} onChange={(e) => setBauleistung(e.target.value)} />
          </Field>
          <Field>
            <Label>Vergabestelle</Label>
            <Input value={vergabestelle} onChange={(e) => setVergabestelle(e.target.value)} />
          </Field>
          <Field>
            <Label>Baustelle</Label>
            <Input value={location} onChange={(e) => setLocation(e.target.value)} />
          </Field>
        </div>
        <Field className="mt-4">
          <Label>Description</Label>
          <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
        </Field>
      </Fieldset>
      {error && <div className="text-sm text-red-600 dark:text-red-400">{error}</div>}
      <div className="flex justify-end gap-2">
        <Button plain type="button" onClick={onBack}>
          Cancel
        </Button>
        <Button type="submit" disabled={!canSubmit}>
          {create.isPending ? 'Creating…' : 'Create Project'}
        </Button>
      </div>
    </form>
  );
}
