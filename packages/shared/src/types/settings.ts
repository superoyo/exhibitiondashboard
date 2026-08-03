/**
 * Runtime-editable settings (the /token page).
 *
 * Both the Apify token and the Claude API key live in the `app_settings` table
 * so an expired key can be swapped from the web UI without a redeploy; when no
 * DB override is set the value falls back to the environment variable.
 */

/** Where the active value came from. */
export type SettingSource = 'database' | 'env';

/** `GET /api/token` and `GET /api/ai/key`. */
export interface SecretInfo {
  masked: string;
  source: SettingSource;
  is_set: boolean;
}

/** `POST /api/token/test` — live Apify credential check. */
export interface TokenTestResult {
  ok: boolean;
  username?: string | null;
  plan?: string | null;
  detail?: string | null;
}

/**
 * `GET /api/ai/status` — Claude availability for the PPTX tie-in feature.
 * `no_credit` is distinct from `invalid_key` on purpose: topping up billing
 * fixes the former without changing the key.
 */
export type AiState = 'ok' | 'no_key' | 'no_credit' | 'invalid_key' | 'error';

export interface AiStatus {
  /** Redundant with `state === 'ok'`, but the backend sends both — keep both. */
  ok: boolean;
  state: AiState;
  message?: string;
}

/** `POST /api/token` and `POST /api/ai/key`. */
export interface SecretSaveResult {
  status: 'saved';
  masked: string;
  source: SettingSource;
  /** Present on the AI key route only — the immediate live re-check. */
  check?: AiStatus;
}
