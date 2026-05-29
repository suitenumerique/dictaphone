// import the original type declarations
import 'i18next'
import layout from '@/locales/en-US/layout.json'
import home from '@/locales/en-US/home.json'
import legals from '@/locales/en-US/legals.json'
import record from '@/locales/en-US/record.json'
import recordings from '@/locales/en-US/recordings.json'
import shared from '@/locales/en-US/shared.json'
import upload from '@/locales/en-US/upload.json'

declare module 'i18next' {
  // Extend CustomTypeOptions
  interface CustomTypeOptions {
    // custom namespace type, if you changed it
    defaultNS: 'home'
    // custom resources type
    resources: {
      layout: typeof layout
      home: typeof home
      legals: typeof legals
      record: typeof record
      recordings: typeof recordings
      shared: typeof shared
      upload: typeof upload
    }
  }
}
