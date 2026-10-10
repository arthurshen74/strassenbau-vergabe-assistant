// A form document's extracted fields as a key/value table, grouped by form section (an XFA
// subform or "Seite n"), in the form's reading order. Checkbox values arrive as ja/nein.

import { Fragment } from 'react';

import { Badge } from '../../components/ui/badge';
import { Text } from '../../components/ui/text';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../../components/ui/table';
import { LoadingState } from '../../components/feedback/LoadingState';
import { ErrorState } from '../../components/feedback/ErrorState';
import type { FormFieldRead } from '../../types/generated';
import type { UseQueryResult } from '@tanstack/react-query';

// Checkbox values written by the server's form extractor (forms/model.py CHECKED/UNCHECKED).
const CHECKED = 'ja';
const UNCHECKED = 'nein';

function groupBySection(fields: FormFieldRead[]): [string, FormFieldRead[]][] {
  const groups: [string, FormFieldRead[]][] = [];
  for (const field of fields) {
    const last = groups[groups.length - 1];
    if (last && last[0] === field.section) last[1].push(field);
    else groups.push([field.section, [field]]);
  }
  return groups;
}

function FieldValue({ value }: { value: string }) {
  if (value === CHECKED) return <Badge color="green">{CHECKED}</Badge>;
  if (value === UNCHECKED) return <Badge color="zinc">{UNCHECKED}</Badge>;
  return <span className="whitespace-pre-wrap break-words">{value}</span>;
}

export function FormFieldsTable({ query }: { query: UseQueryResult<FormFieldRead[]> }) {
  if (query.isPending) return <LoadingState label="Loading form fields…" />;
  if (query.isError) {
    return <ErrorState message={(query.error as Error).message} onRetry={() => query.refetch()} />;
  }
  if (query.data.length === 0) {
    return <Text>No form fields extracted (not yet ingested, or skipped).</Text>;
  }
  return (
    <Table dense>
      <TableHead>
        <TableRow>
          <TableHeader>Feld</TableHeader>
          <TableHeader>Wert</TableHeader>
          <TableHeader className="w-0">Seite</TableHeader>
        </TableRow>
      </TableHead>
      <TableBody>
        {groupBySection(query.data).map(([section, fields], index) => (
          <Fragment key={`${section}-${index}`}>
            <TableRow>
              <TableCell
                colSpan={3}
                className="bg-zinc-50 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:bg-white/5 dark:text-zinc-400"
              >
                {section}
              </TableCell>
            </TableRow>
            {fields.map((f) => (
              <TableRow key={f.field_order}>
                <TableCell className="max-w-xs whitespace-normal break-words" title={f.name}>
                  {f.label ?? f.name}
                </TableCell>
                <TableCell className="max-w-md whitespace-normal">
                  <FieldValue value={f.value} />
                </TableCell>
                <TableCell className="text-zinc-500">{f.page}</TableCell>
              </TableRow>
            ))}
          </Fragment>
        ))}
      </TableBody>
    </Table>
  );
}
