import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import { defaultLanguage, resources } from './resources';
import { getLocales } from 'react-native-localize';

const possibleLocales = new Set(['fr', 'en']);

const userLocales = getLocales()
  .map(locale => locale.languageCode.split(' ')[0])
  .filter(locale => possibleLocales.has(locale));

if (!i18n.isInitialized) {
  i18n.use(initReactI18next).init({
    lng: userLocales[0] ?? defaultLanguage,
    compatibilityJSON: 'v4',
    fallbackLng: defaultLanguage,
    interpolation: {
      escapeValue: false,
    },
    resources,
  });
}

export default i18n;
