export type ApiUser = {
  id: string
  email: string | null
  full_name: string | null
  last_name: string | null
  language: 'fr-fr' | 'en-us'
  timezone: string
  flag_show_mobile_app_popup: boolean
}
