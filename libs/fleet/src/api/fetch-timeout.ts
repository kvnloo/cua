/** Default deadline for non-streaming fleet webapp API requests.
 *
 * Every fleet api/* fetcher issues plain fetch() with no AbortSignal: a stalled
 * connection hangs the settings/billing/usage pages forever with no way out.
 * Streaming calls (chat.ts streamTurn) are excluded — a hard deadline would
 * kill long generations; those get an idle-based timeout instead.
 */
export const FLEET_API_FETCH_TIMEOUT_MS = 30_000

/**
 * Combine a caller-provided signal with the default fetch timeout.
 * The request aborts on whichever fires first; callers can still abort early.
 */
export function fleetTimeoutSignal(signal?: AbortSignal | null): AbortSignal {
  const timeout = AbortSignal.timeout(FLEET_API_FETCH_TIMEOUT_MS)
  return signal ? AbortSignal.any([signal, timeout]) : timeout
}
