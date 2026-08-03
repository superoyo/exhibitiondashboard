/**
 * An error carrying an HTTP status and a client-safe message.
 *
 * The message is rendered as `detail`, matching the Python app's error shape so
 * the existing frontend error handling keeps working unchanged.
 */
export class AppError extends Error {
  readonly status: number;
  /** True when the message is safe to show a user (it is Thai UI copy). */
  readonly expose: boolean;

  constructor(status: number, message: string, expose = true) {
    super(message);
    this.name = 'AppError';
    this.status = status;
    this.expose = expose;
  }

  static badRequest(message: string) {
    return new AppError(400, message);
  }

  static unauthorized(message = 'unauthorized — กรุณาเข้าสู่ระบบ') {
    return new AppError(401, message);
  }

  static notFound(message: string) {
    return new AppError(404, message);
  }

  static conflict(message: string) {
    return new AppError(409, message);
  }
}
