import { Heading } from '../ui/heading';
import { Text } from '../ui/text';

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-3 p-8 text-center">
      <Heading level={3}>{title}</Heading>
      {description && (
        <Text className="max-w-md">{description}</Text>
      )}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
