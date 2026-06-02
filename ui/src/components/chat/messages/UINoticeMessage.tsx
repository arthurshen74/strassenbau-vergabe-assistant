export function UINoticeMessage({ content }: { content: string }) {
  return (
    <div className="flex justify-center">
      <div className="text-xs italic text-zinc-500 dark:text-zinc-400">
        {content}
      </div>
    </div>
  );
}
