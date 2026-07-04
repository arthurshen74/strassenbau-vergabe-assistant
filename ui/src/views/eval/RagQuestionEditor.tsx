// Form for one RAG reference question, used for both create (empty initial) and
// edit. Refs are picked from the project's ingested documents plus a page number;
// the server re-validates (document ownership, page bounds) on save.

import { useState } from 'react';
import { XMarkIcon } from '@heroicons/react/16/solid';
import { Button } from '../../components/ui/button';
import { Field, Label } from '../../components/ui/fieldset';
import { Input } from '../../components/ui/input';
import { Select } from '../../components/ui/select';
import { Text } from '../../components/ui/text';
import { Textarea } from '../../components/ui/textarea';
import type {
  DocumentRead,
  RagGroundTruthRead,
  RagGroundTruthUpsert,
  RagRef,
} from '../../types/generated';

const QUESTION_TYPES: {
  value: RagGroundTruthUpsert['question_type'];
  label: string;
}[] = [
  { value: 'lookup', label: 'Lookup' },
  { value: 'aggregation', label: 'Aggregation' },
  { value: 'multi_hop', label: 'Multi-Hop' },
  { value: 'constraint_surfacing', label: 'Constraint-Surfacing' },
  { value: 'cross_doc_conditional', label: 'Cross-Doc-Conditional' },
];

const CATEGORIES: { value: RagGroundTruthUpsert['category']; label: string }[] = [
  { value: 'kalkulator', label: 'Kalkulator' },
  { value: 'bauleiter', label: 'Bauleiter' },
];

export function RagQuestionEditor({
  initial,
  documents,
  saving,
  errorMessage,
  onSave,
  onCancel,
}: {
  initial: RagGroundTruthRead | null;
  documents: DocumentRead[];
  saving: boolean;
  errorMessage: string | null;
  onSave: (body: RagGroundTruthUpsert) => void;
  onCancel: () => void;
}) {
  const [question, setQuestion] = useState(initial?.question ?? '');
  const [goldAnswer, setGoldAnswer] = useState(initial?.gold_answer ?? '');
  const [questionType, setQuestionType] = useState<
    RagGroundTruthUpsert['question_type']
  >(initial?.question_type ?? 'lookup');
  const [category, setCategory] = useState<RagGroundTruthUpsert['category']>(
    initial?.category ?? 'kalkulator',
  );
  const [refs, setRefs] = useState<RagRef[]>(initial?.refs ?? []);
  const [refDocument, setRefDocument] = useState('');
  const [refPage, setRefPage] = useState('');

  const docName = (uuid: string) =>
    documents.find((d) => d.document_uuid === uuid)?.file_name ?? uuid;

  const addRef = () => {
    const page = Number(refPage);
    if (!refDocument || !Number.isInteger(page) || page < 1) return;
    if (refs.some((r) => r.document_uuid === refDocument && r.page === page)) return;
    setRefs((r) => [...r, { document_uuid: refDocument, page }]);
    setRefPage('');
  };

  const submit = () =>
    onSave({
      question: question.trim(),
      gold_answer: goldAnswer.trim(),
      refs,
      question_type: questionType,
      category,
    });

  return (
    <div className="flex flex-col gap-4 py-2">
      <Field>
        <Label>Frage</Label>
        <Textarea
          rows={2}
          value={question}
          disabled={saving}
          onChange={(e) => setQuestion(e.target.value)}
        />
      </Field>

      <div className="grid max-w-lg grid-cols-1 gap-4 sm:grid-cols-2">
        <Field>
          <Label>Typ</Label>
          <Select
            value={questionType}
            disabled={saving}
            onChange={(e) =>
              setQuestionType(
                e.target.value as RagGroundTruthUpsert['question_type'],
              )
            }
          >
            {QUESTION_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field>
          <Label>Kategorie</Label>
          <Select
            value={category}
            disabled={saving}
            onChange={(e) =>
              setCategory(e.target.value as RagGroundTruthUpsert['category'])
            }
          >
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      <Field>
        <Label>Gold-Antwort</Label>
        <Textarea
          rows={3}
          value={goldAnswer}
          disabled={saving}
          onChange={(e) => setGoldAnswer(e.target.value)}
        />
      </Field>

      <div className="flex flex-col gap-2">
        {/* Group heading, not a control label — a Catalyst <Label> throws outside a Field. */}
        <span className="text-base/6 text-zinc-950 select-none sm:text-sm/6 dark:text-white">
          Referenzen (Fundstellen)
        </span>
        {refs.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {refs.map((r) => (
              <span
                key={`${r.document_uuid}:${r.page}`}
                className="inline-flex items-center gap-1.5 rounded-md border border-blue-500/20 bg-blue-50 py-1 pr-1 pl-2 font-mono text-xs text-blue-700 dark:bg-blue-950/40 dark:text-blue-300"
              >
                {docName(r.document_uuid)}::S.{r.page}
                <button
                  type="button"
                  aria-label="Referenz entfernen"
                  disabled={saving}
                  className="rounded p-0.5 opacity-60 hover:opacity-100"
                  onClick={() =>
                    setRefs((all) =>
                      all.filter(
                        (x) =>
                          !(
                            x.document_uuid === r.document_uuid &&
                            x.page === r.page
                          ),
                      ),
                    )
                  }
                >
                  <XMarkIcon className="h-3.5 w-3.5" />
                </button>
              </span>
            ))}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Select
            className="max-w-64"
            value={refDocument}
            disabled={saving}
            aria-label="Dokument wählen"
            onChange={(e) => setRefDocument(e.target.value)}
          >
            <option value="">Dokument wählen…</option>
            {documents.map((d) => (
              <option key={d.document_uuid} value={d.document_uuid}>
                {d.file_name}
              </option>
            ))}
          </Select>
          <Input
            className="max-w-24"
            type="number"
            min={1}
            placeholder="Seite"
            value={refPage}
            disabled={saving}
            aria-label="Seite"
            onChange={(e) => setRefPage(e.target.value)}
          />
          <Button outline disabled={saving} onClick={addRef}>
            Hinzufügen
          </Button>
          <span className="text-xs text-zinc-400">
            nur ingestierte Dokumente wählbar
          </span>
        </div>
        {refs.length === 0 && (
          <Text className="text-xs">
            Ohne Referenzen zählt die Frage nur in die Antwort-Bewertung, nicht
            in die Retrieval-Metriken.
          </Text>
        )}
      </div>

      {errorMessage && (
        <Text className="text-xs text-red-600 dark:text-red-400">
          {errorMessage}
        </Text>
      )}

      <div className="flex items-center gap-2">
        <Button
          disabled={saving || question.trim() === '' || goldAnswer.trim() === ''}
          onClick={submit}
        >
          Speichern
        </Button>
        <Button plain disabled={saving} onClick={onCancel}>
          Abbrechen
        </Button>
      </div>
    </div>
  );
}
