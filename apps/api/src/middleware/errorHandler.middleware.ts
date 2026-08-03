import type { ErrorRequestHandler, RequestHandler } from 'express';
import { ZodError } from 'zod';

import { logger } from '../config/logger.js';
import { AppError } from '../utils/AppError.js';

/** 404 for any /api path no route matched. */
export const notFoundHandler: RequestHandler = (_req, res) => {
  res.status(404).json({ detail: 'not found' });
};

/**
 * Terminal error handler.
 *
 * Responses use `{ detail }` — the same shape FastAPI produces — so the
 * frontend's `apiErrorMessage()` keeps working without a special case.
 *
 * Unexpected errors are logged in full but answered with a generic message: a
 * stack trace or driver error can name tables and columns, and this API is
 * reachable from the public internet.
 */
export const errorHandler: ErrorRequestHandler = (err, req, res, _next) => {
  if (err instanceof AppError) {
    if (err.status >= 500) logger.error({ err, path: req.path }, 'Request failed');
    res.status(err.status).json({ detail: err.message });
    return;
  }

  if (err instanceof ZodError) {
    // Surface the first validation message; the frontend shows exactly one.
    const first = err.issues[0];
    const where = first?.path.join('.');
    res.status(400).json({
      detail: first?.message ?? 'ข้อมูลไม่ถูกต้อง',
      ...(where ? { field: where } : {}),
    });
    return;
  }

  logger.error({ err, path: req.path, method: req.method }, 'Unhandled error');
  res.status(500).json({ detail: 'เกิดข้อผิดพลาดภายในระบบ' });
};
