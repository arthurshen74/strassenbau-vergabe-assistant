// appconstants.ts

export const APP_CONSTANTS = {
  STALE_TIMEOUT_MS: 1000 * 60 * 5, // 5 minutes
  API_TIMEOUT_MS: 1000 * 30, // 30 seconds — default for fast REST calls
  LLM_API_TIMEOUT_MS: 1000 * 120, // 2 minutes — for synchronous LLM-backed endpoints
  MAX_RETRIES: 3,
} as const;

// Optional convenience type if you ever need it
export type AppConstants = typeof APP_CONSTANTS;
