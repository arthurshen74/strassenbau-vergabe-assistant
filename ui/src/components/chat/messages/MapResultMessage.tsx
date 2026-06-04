// Renders a render_map tool result inline: the 640px static map image, proxied from object
// storage via the project-scoped maps endpoint. The image is natively 640px and scales down to
// fit narrower thread columns (never up). Falls back to an inline error line when the map could
// not be generated (e.g. the Static Maps key is missing or the request failed).

import { apiBase } from '../../../api/client';

const RESULT_MAP_ID = 'map_id';
const RESULT_MAP_ADDRESS = 'address';
const RESULT_MAP_ERROR = 'error';

function asString(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

function mapUrl(projectUuid: string, mapId: string): string {
  return `${apiBase}/projects/${projectUuid}/maps/${mapId}`;
}

export function MapResultMessage({
  data,
  projectUuid,
}: {
  data: Record<string, unknown> | null;
  projectUuid?: string;
}) {
  const error = asString(data?.[RESULT_MAP_ERROR]);
  if (error) {
    return (
      <div className="flex justify-start">
        <div className="max-w-2xl rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300">
          Karte konnte nicht erzeugt werden: {error}
        </div>
      </div>
    );
  }

  const mapId = asString(data?.[RESULT_MAP_ID]);
  const address = asString(data?.[RESULT_MAP_ADDRESS]);
  if (!mapId || !projectUuid) return null;

  return (
    <div className="flex justify-start">
      <div className="rounded-lg border border-zinc-200 bg-white/50 p-2 dark:border-zinc-700 dark:bg-zinc-800/30">
        <img
          src={mapUrl(projectUuid, mapId)}
          alt={address ? `Karte: ${address}` : 'Karte'}
          width={640}
          height={640}
          className="h-auto w-full max-w-[640px] rounded"
        />
        {address && (
          <div className="mt-1 px-1 text-xs text-zinc-500 dark:text-zinc-400">{address}</div>
        )}
      </div>
    </div>
  );
}
