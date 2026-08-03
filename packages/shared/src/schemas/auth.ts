import { z } from 'zod';

/**
 * Login input. Shared so the Express side validates exactly what the React
 * form guarantees — one definition, no drift.
 */
export const loginInputSchema = z.object({
  username: z.string().trim().min(1, 'กรุณากรอกชื่อผู้ใช้'),
  password: z.string().min(1, 'กรุณากรอกรหัสผ่าน'),
});

export type LoginInput = z.infer<typeof loginInputSchema>;
