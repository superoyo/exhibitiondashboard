import { z } from 'zod';

/**
 * Secret-setting inputs. The messages are the ones the current backend
 * returns, so the UI copy does not change when validation moves to Express.
 */

export const apifyTokenInputSchema = z.object({
  token: z.string().trim().min(10, 'Token สั้นเกินไป ดูเหมือนไม่ถูกต้อง'),
});

export const anthropicKeyInputSchema = z.object({
  token: z
    .string()
    .trim()
    .min(20, 'รูปแบบ key ไม่ถูกต้อง — ต้องขึ้นต้นด้วย sk-ant-')
    .refine((v) => v.startsWith('sk-ant-'), {
      message: 'รูปแบบ key ไม่ถูกต้อง — ต้องขึ้นต้นด้วย sk-ant-',
    }),
});

export type ApifyTokenInput = z.infer<typeof apifyTokenInputSchema>;
export type AnthropicKeyInput = z.infer<typeof anthropicKeyInputSchema>;
