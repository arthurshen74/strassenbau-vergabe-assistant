// Editable form for adding or modifying a position.
//
// We chose a custom form over the generic <SchemaForm> renderer because
// position has three things that fight a generic field-driven layout:
//   - paired salary range (two number inputs that validate against each
//     other),
//   - remote → location relationship (location only matters when not
//     remote, but is allowed in either case),
//   - skills as an array of {skill, proficiency} rows with a chip-style
//     removal affordance and a per-row enum for proficiency.
//
// Once we have ≥3 form-driven shapes (eval configs, prompts, etc.)
// competing for layout, revisit moving the simple ones to <SchemaForm>;
// position will probably stay custom.
//
// The component is uncontrolled-ish: it owns its working draft in local
// state, seeded from `initialValues`. Submit produces a fully-typed body
// matching `PositionFieldsBody` (for create) or `ModifyPositionBody` (for
// modify); the parent decides which mutation to call. We don't take a
// mutation callback directly because the inline-card-in-chat use case
// and the paste-text use case both want their own success UI.

import { useState } from 'react';
import { Heading } from '../../../components/ui/heading';
import { Input } from '../../../components/ui/input';
import { Textarea } from '../../../components/ui/textarea';
import { Select } from '../../../components/ui/select';
import { Switch } from '../../../components/ui/switch';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import {
  Field,
  Fieldset,
  Label,
  Legend,
} from '../../../components/ui/fieldset';
import { XMarkIcon, PlusIcon } from '@heroicons/react/16/solid';
import type {
  ExtractedPositionDTO,
  PositionFieldsBody,
  PositionVersionDTO,
  SkillRequirementBody,
} from '../../../types/generated';

type PositionLevel = PositionFieldsBody['level'];
type ProficiencyLevel = SkillRequirementBody['proficiency'];

const LEVELS: PositionLevel[] = ['junior', 'mid', 'senior', 'staff'];
const PROFICIENCIES: ProficiencyLevel[] = [
  'novice',
  'practitioner',
  'advanced',
  'expert',
];

interface PositionFormState {
  title: string;
  company: string;
  department: string;
  level: PositionLevel;
  salary_min: string; // string-typed so the user can clear the field
  salary_max: string;
  remote: boolean;
  location: string;
  skills: SkillRequirementBody[];
  description: string;
  notes: string;
}

function emptyState(): PositionFormState {
  return {
    title: '',
    company: '',
    department: '',
    level: 'mid',
    salary_min: '',
    salary_max: '',
    remote: false,
    location: '',
    skills: [],
    description: '',
    notes: '',
  };
}

function fromExtracted(dto: ExtractedPositionDTO): PositionFormState {
  return {
    title: dto.title ?? '',
    company: dto.company ?? '',
    department: dto.department ?? '',
    level: dto.level ?? 'mid',
    salary_min: dto.salary_min != null ? String(dto.salary_min) : '',
    salary_max: dto.salary_max != null ? String(dto.salary_max) : '',
    remote: dto.remote ?? false,
    location: dto.location ?? '',
    skills: dto.skills ?? [],
    description: dto.description ?? '',
    notes: dto.notes ?? '',
  };
}

function fromVersion(v: PositionVersionDTO): PositionFormState {
  return {
    title: v.title,
    company: v.company,
    department: v.department,
    level: v.level,
    salary_min: v.salary_min != null ? String(v.salary_min) : '',
    salary_max: v.salary_max != null ? String(v.salary_max) : '',
    remote: v.remote,
    location: v.location ?? '',
    skills: v.skills,
    description: v.description ?? '',
    notes: v.notes ?? '',
  };
}

export interface PositionFormProps {
  /** Pre-fill source. Pick one. */
  extracted?: ExtractedPositionDTO;
  initialVersion?: PositionVersionDTO;
  /** Header title; varies by use-case ("Review extracted position", "Edit position", etc.) */
  heading?: string;
  /** "Save" / "Save changes" — varies by mode. */
  submitLabel?: string;
  /** Called with a fully-validated PositionFieldsBody when the user clicks save. */
  onSubmit: (body: PositionFieldsBody) => Promise<void> | void;
  onCancel: () => void;
  submitting?: boolean;
  /** Server-supplied error message to surface inline above the actions. */
  errorMessage?: string | null;
}

export function PositionForm({
  extracted,
  initialVersion,
  heading = 'Position',
  submitLabel = 'Save',
  onSubmit,
  onCancel,
  submitting = false,
  errorMessage,
}: PositionFormProps) {
  const [state, setState] = useState<PositionFormState>(() => {
    if (initialVersion) return fromVersion(initialVersion);
    if (extracted) return fromExtracted(extracted);
    return emptyState();
  });
  const [localError, setLocalError] = useState<string | null>(null);

  const update = <K extends keyof PositionFormState>(
    key: K,
    value: PositionFormState[K],
  ) => {
    setState((s) => ({ ...s, [key]: value }));
  };

  const updateSkill = (
    idx: number,
    patch: Partial<SkillRequirementBody>,
  ) => {
    setState((s) => ({
      ...s,
      skills: s.skills.map((sk, i) => (i === idx ? { ...sk, ...patch } : sk)),
    }));
  };

  const addSkill = () =>
    setState((s) => ({
      ...s,
      skills: [...s.skills, { skill: '', proficiency: 'practitioner' }],
    }));

  const removeSkill = (idx: number) =>
    setState((s) => ({
      ...s,
      skills: s.skills.filter((_, i) => i !== idx),
    }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);

    // Required fields. The server enforces these too, but failing early
    // here gives the user a clearer message than a 422 round-trip.
    if (!state.title.trim()) return setLocalError('Title is required.');
    if (!state.company.trim()) return setLocalError('Company is required.');
    if (!state.department.trim())
      return setLocalError('Department is required.');

    const min = state.salary_min ? Number(state.salary_min) : null;
    const max = state.salary_max ? Number(state.salary_max) : null;
    if (min != null && max != null && min > max) {
      return setLocalError('Salary minimum must be ≤ maximum.');
    }

    // Skip blank skill rows so the user isn't punished for clicking
    // "+ Add skill" and changing their mind.
    const skills = state.skills.filter((s) => s.skill.trim().length > 0);

    const body: PositionFieldsBody = {
      title: state.title.trim(),
      company: state.company.trim(),
      department: state.department.trim(),
      level: state.level,
      salary_min: min,
      salary_max: max,
      remote: state.remote,
      location: state.location.trim() || null,
      skills,
      description: state.description.trim() || null,
      notes: state.notes.trim() || null,
    };
    await onSubmit(body);
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <Heading level={4}>{heading}</Heading>

      <Fieldset>
        <Legend>Role</Legend>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field>
            <Label>Title</Label>
            <Input
              value={state.title}
              onChange={(e) => update('title', e.target.value)}
              required
            />
          </Field>
          <Field>
            <Label>Company</Label>
            <Input
              value={state.company}
              onChange={(e) => update('company', e.target.value)}
              required
            />
          </Field>
          <Field>
            <Label>Department</Label>
            <Input
              value={state.department}
              onChange={(e) => update('department', e.target.value)}
              required
            />
          </Field>
          <Field>
            <Label>Level</Label>
            <Select
              value={state.level}
              onChange={(e) =>
                update('level', e.target.value as PositionLevel)
              }
            >
              {LEVELS.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </Fieldset>

      <Fieldset>
        <Legend>Compensation & location</Legend>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field>
            <Label>Salary min (USD)</Label>
            <Input
              type="number"
              min={0}
              value={state.salary_min}
              onChange={(e) => update('salary_min', e.target.value)}
            />
          </Field>
          <Field>
            <Label>Salary max (USD)</Label>
            <Input
              type="number"
              min={0}
              value={state.salary_max}
              onChange={(e) => update('salary_max', e.target.value)}
            />
          </Field>
          <Field className="flex items-center gap-3">
            <Label>Remote</Label>
            <Switch
              checked={state.remote}
              onChange={(checked) => update('remote', checked)}
            />
          </Field>
          <Field>
            <Label>Location</Label>
            <Input
              value={state.location}
              onChange={(e) => update('location', e.target.value)}
              placeholder={state.remote ? 'Optional for remote' : 'City, region'}
            />
          </Field>
        </div>
      </Fieldset>

      <Fieldset>
        <Legend>Skills</Legend>
        <div className="flex flex-col gap-2">
          {state.skills.length === 0 && (
            <div className="text-xs text-zinc-500">
              No skills yet. Add the ones the role requires so the
              interviewer can ask about them.
            </div>
          )}
          {state.skills.map((s, i) => (
            <div key={i} className="flex items-center gap-2">
              {/*
               * The Input must have flex-1 so it grows to fill remaining
               * space. However, the Catalyst Select component hardcodes
               * `w-full` on its outer <span>, which makes that span a flex
               * item with flex-basis ≈ 100% of the container. When paired
               * with the Input's flex-basis: 0%, the Select claims all the
               * space and the Input collapses to zero width (skill name
               * invisible). Fix: wrap the Select in a fixed-width, shrink-0
               * container so the flex algorithm sees a bounded peer and
               * leaves room for the Input to grow.
               */}
              <Input
                aria-label={`Skill ${i + 1}`}
                value={s.skill}
                onChange={(e) => updateSkill(i, { skill: e.target.value })}
                placeholder="e.g. Python"
                className="flex-1 min-w-0"
              />
              <div className="w-40 shrink-0">
                <Select
                  aria-label={`Proficiency for skill ${i + 1}`}
                  value={s.proficiency}
                  onChange={(e) =>
                    updateSkill(i, {
                      proficiency: e.target.value as ProficiencyLevel,
                    })
                  }
                >
                  {PROFICIENCIES.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </Select>
              </div>
              <Button
                type="button"
                plain
                onClick={() => removeSkill(i)}
                aria-label={`Remove skill ${i + 1}`}
              >
                <XMarkIcon />
              </Button>
            </div>
          ))}
          <div>
            <Button type="button" outline onClick={addSkill}>
              <PlusIcon />
              Add skill
            </Button>
          </div>
        </div>
      </Fieldset>

      <Fieldset>
        <Legend>Description & notes</Legend>
        <div className="flex flex-col gap-3">
          <Field>
            <Label>Description</Label>
            <Textarea
              rows={3}
              value={state.description}
              onChange={(e) => update('description', e.target.value)}
              placeholder="A short summary of the role."
            />
          </Field>
          <Field>
            <Label>Notes</Label>
            <Textarea
              rows={2}
              value={state.notes}
              onChange={(e) => update('notes', e.target.value)}
              placeholder="Anything you want the interviewer to know."
            />
          </Field>
        </div>
      </Fieldset>

      {(localError || errorMessage) && (
        <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-700/50 dark:bg-red-950/30 dark:text-red-300">
          {localError || errorMessage}
        </div>
      )}

      <div className="flex items-center justify-end gap-2">
        <Badge color="zinc">unsaved</Badge>
        <Button type="button" plain onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
        <Button type="submit" disabled={submitting}>
          {submitting ? 'Saving…' : submitLabel}
        </Button>
      </div>
    </form>
  );
}
