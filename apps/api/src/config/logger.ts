import pino from 'pino';

import { env } from './env.js';

/**
 * Structured logging.
 *
 * `redact` is not cosmetic: Authorization headers carry live Wazzup tokens and
 * the Apify/Anthropic keys move through request bodies, and Railway's log drain
 * is long-lived. Anything sensitive must never reach it.
 */
export const logger = pino({
  level: env.LOG_LEVEL,
  redact: {
    paths: [
      'req.headers.authorization',
      'req.headers["x-admin-key"]',
      'req.headers.cookie',
      '*.token',
      '*.password',
      '*.image_base64',
    ],
    censor: '[redacted]',
  },
  // Pretty output locally; JSON in production so the log drain can parse it.
  ...(env.isProduction
    ? {}
    : { transport: { target: 'pino-pretty', options: { translateTime: 'HH:MM:ss', ignore: 'pid,hostname' } } }),
});
