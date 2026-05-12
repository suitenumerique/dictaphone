import { z } from 'zod/v4'

export const appLanguageSchema = z.enum(['en', 'fr'])

export const appSettingsSchema = z.object({
  language: appLanguageSchema,
  wifiOnlyUpload: z.boolean().default(true),
})

export type AppLanguage = z.infer<typeof appLanguageSchema>
export type AppSettings = z.infer<typeof appSettingsSchema>
