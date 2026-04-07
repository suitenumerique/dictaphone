import React, { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Switch, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import i18n from '../i18n';
import { getSettings, setSettings } from '../services/storage';
import type { AppLanguage } from '../types/settings';
import { LoginWithProConnectButton } from '../components/LoginWithProConnectButton';

export default function SettingsScreen() {
  const { t } = useTranslation();
  const [allowNetworkSync, setAllowNetworkSync] = useState(false);
  const [language, setLanguage] = useState<AppLanguage>('en');

  useEffect(() => {
    const settings = getSettings();
    setAllowNetworkSync(settings.allowNetworkSync);
    setLanguage(settings.language);
    i18n.changeLanguage(settings.language).catch(() => undefined);
  }, []);

  const persistSettings = (
    nextNetworkSync: boolean,
    nextLanguage: AppLanguage,
  ) => {
    setSettings({
      allowNetworkSync: nextNetworkSync,
      language: nextLanguage,
    });
  };

  const handleToggleNetworkSync = (value: boolean) => {
    setAllowNetworkSync(value);
    persistSettings(value, language);
  };

  const handleChangeLanguage = (nextLanguage: AppLanguage) => {
    setLanguage(nextLanguage);
    persistSettings(allowNetworkSync, nextLanguage);
    i18n.changeLanguage(nextLanguage).catch(() => undefined);
  };

  return (
    <View style={styles.container}>
      <LoginWithProConnectButton />
      <View style={styles.card}>
        <View style={styles.rowBetween}>
          <Text style={styles.label}>{t('settings.networkSync')}</Text>
          <Switch
            value={allowNetworkSync}
            onValueChange={handleToggleNetworkSync}
          />
        </View>
      </View>
      <View style={styles.card}>
        <Text style={styles.label}>{t('settings.language')}</Text>
        <View style={styles.languageRow}>
          <Pressable
            style={[
              styles.languageButton,
              language === 'en' && styles.languageButtonActive,
            ]}
            onPress={() => handleChangeLanguage('en')}
          >
            <Text
              style={[
                styles.languageButtonText,
                language === 'en' && styles.languageButtonTextActive,
              ]}
            >
              {t('settings.english')}
            </Text>
          </Pressable>

          <Pressable
            style={[
              styles.languageButton,
              language === 'fr' && styles.languageButtonActive,
            ]}
            onPress={() => handleChangeLanguage('fr')}
          >
            <Text
              style={[
                styles.languageButtonText,
                language === 'fr' && styles.languageButtonTextActive,
              ]}
            >
              {t('settings.french')}
            </Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F9FAFB',
    padding: 16,
    paddingTop: 36,
    gap: 14,
  },
  title: {
    fontSize: 32,
    fontWeight: '800',
    color: '#111827',
    marginBottom: 4,
  },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 14,
    gap: 12,
    shadowColor: '#111827',
    shadowOpacity: 0.06,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  rowBetween: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
  },
  label: {
    flexWrap: 'wrap',
    flexShrink: 1,
    fontSize: 16,
    fontWeight: '600',
    color: '#1F2937',
  },
  languageRow: {
    flexDirection: 'row',
    gap: 10,
  },
  languageButton: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#D1D5DB',
    paddingHorizontal: 14,
    paddingVertical: 10,
    backgroundColor: '#FFFFFF',
  },
  languageButtonActive: {
    borderColor: '#1D4ED8',
    backgroundColor: '#DBEAFE',
  },
  languageButtonText: {
    color: '#374151',
    fontWeight: '600',
  },
  languageButtonTextActive: {
    color: '#1E3A8A',
  },
});
