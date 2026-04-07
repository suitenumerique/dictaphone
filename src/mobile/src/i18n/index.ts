import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import { defaultLanguage, resources } from './resources';

if (!i18n.isInitialized) {
  i18n.use(initReactI18next).init({
    compatibilityJSON: 'v4',
    fallbackLng: defaultLanguage,
    interpolation: {
      escapeValue: false,
    },
    lng: defaultLanguage,
    resources,
  });
}

export default i18n;
