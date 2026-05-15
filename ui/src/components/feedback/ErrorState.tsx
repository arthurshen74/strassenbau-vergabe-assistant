import { Heading } from '../ui/heading';
import { Text } from '../ui/text';
import { Button } from '../ui/button';

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ title = 'Something went wrong', message, onRetry }: ErrorStateProps) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-3 p-8 text-center">
      <Heading level={3}>{title}</Heading>
      <Text className="max-w-md">{message}</Text>
      {onRetry && (
        <Button onClick={onRetry} className="mt-2">
          Try again
        </Button>
      )}
    </div>
  );
}
