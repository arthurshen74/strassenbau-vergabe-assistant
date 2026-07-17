// Entity Rules admin page (MainWindow view): the full ruleset in one table —
// label, pattern preview, pattern id, an inline enabled toggle, and edit/delete
// actions — plus an "Add Rule" button. Every mutation invalidates the list, and
// the server marks the spaCy ruler dirty so the next analysis reflects the change.

import { useMemo, useState } from 'react';

import {
  useDeleteEntityRule,
  useEntityRuleLabels,
  useEntityRules,
  useUpdateEntityRule,
} from '../../api/entityRules';
import type { EntityRuleRead } from '../../types/generated';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Switch } from '../../components/ui/switch';
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
import { EntityRuleEditDialog } from './EntityRuleEditDialog';

function patternPreview(pattern: EntityRuleRead['pattern']): string {
  return typeof pattern === 'string' ? `"${pattern}"` : JSON.stringify(pattern);
}

export function EntityRulesView() {
  const rules = useEntityRules();
  const labelsQuery = useEntityRuleLabels();
  const update = useUpdateEntityRule();
  const del = useDeleteEntityRule();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<EntityRuleRead | null>(null);

  const labels = useMemo(() => labelsQuery.data ?? [], [labelsQuery.data]);

  const openCreate = () => {
    setEditing(null);
    setDialogOpen(true);
  };
  const openEdit = (rule: EntityRuleRead) => {
    setEditing(rule);
    setDialogOpen(true);
  };

  const toggle = (rule: EntityRuleRead) => {
    update.mutate({
      uuid: rule.entity_rule_uuid,
      body: { enabled: !rule.enabled },
    });
  };

  const remove = (rule: EntityRuleRead) => {
    if (window.confirm(`Delete rule for "${rule.label}"?`)) {
      del.mutate(rule.entity_rule_uuid);
    }
  };

  if (rules.isPending) return <LoadingState label="Loading entity rules…" />;
  if (rules.isError) return <ErrorState message="Failed to load entity rules." />;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <span className="text-sm text-zinc-500">
          {rules.data.length} rules
        </span>
        <Button onClick={openCreate}>Add Rule</Button>
      </div>

      <Table dense>
        <TableHead>
          <TableRow>
            <TableHeader>Label</TableHeader>
            <TableHeader>Pattern</TableHeader>
            <TableHeader>Pattern ID</TableHeader>
            <TableHeader>Enabled</TableHeader>
            <TableHeader className="text-right">Actions</TableHeader>
          </TableRow>
        </TableHead>
        <TableBody>
          {rules.data.map((rule) => (
            <TableRow key={rule.entity_rule_uuid}>
              <TableCell>
                <Badge color="blue">{rule.label}</Badge>
              </TableCell>
              <TableCell className="max-w-md truncate font-mono text-xs text-zinc-600 dark:text-zinc-400">
                {patternPreview(rule.pattern)}
              </TableCell>
              <TableCell className="font-mono text-xs text-zinc-500">
                {rule.pattern_id ?? '—'}
              </TableCell>
              <TableCell>
                <Switch
                  checked={rule.enabled}
                  onChange={() => toggle(rule)}
                />
              </TableCell>
              <TableCell className="text-right">
                <div className="flex justify-end gap-2">
                  <Button plain onClick={() => openEdit(rule)}>
                    Edit
                  </Button>
                  <Button plain onClick={() => remove(rule)}>
                    Delete
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <EntityRuleEditDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        rule={editing}
        labels={labels}
      />
    </div>
  );
}
