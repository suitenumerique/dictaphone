import React, { useCallback, useMemo, useState } from 'react'
import {
  Dimensions,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from 'react-native'
import { useNavigation } from '@react-navigation/core'
import type { NativeStackNavigationProp } from '@react-navigation/native-stack'
import { useTranslation } from 'react-i18next'
import { Lucide } from '@react-native-vector-icons/lucide'
import { InAppBrowser } from 'react-native-inappbrowser-reborn'
import Popover from 'react-native-popover-view'
import DeviceInfo from 'react-native-device-info'
import type { RootStackParamList } from '@/navigation/types'
import { useInsets } from '@/utils/useInsets'
import { useUser } from '@/features/auth/api/useUser'
import { useResetNavigationHistory } from '@/navigation/useRestNavigationHistory'
import { AppText } from '@/components/AppText'
import { BASE_URL } from '@/api/constants'
import { colors } from '@/components/colors'
// @ts-expect-error Icon
import LogoWithName from '../assets/logo-with-name.svg'

type InfoTranslationKey =
  | 'legalTerms'
  | 'legalTermsUrl'
  | 'termsOfService'
  | 'termsOfServiceUrl'
  | 'personalData'
  | 'personalDataUrl'
  | 'accessibility'
  | 'accessibilityUrl'

type LegalDocument = {
  labelKey: InfoTranslationKey
  urlKey: InfoTranslationKey
}

type AppLanguage = 'en' | 'fr'
type ApiLanguage = 'en-us' | 'fr-fr'

type LanguageOption = {
  appLanguage: AppLanguage
  apiLanguage: ApiLanguage
}

const LEGAL_DOCUMENTS: LegalDocument[] = [
  { labelKey: 'legalTerms', urlKey: 'legalTermsUrl' },
  { labelKey: 'termsOfService', urlKey: 'termsOfServiceUrl' },
  { labelKey: 'personalData', urlKey: 'personalDataUrl' },
  { labelKey: 'accessibility', urlKey: 'accessibilityUrl' },
]

const LANGUAGE_OPTIONS: LanguageOption[] = [
  { appLanguage: 'fr', apiLanguage: 'fr-fr' },
  { appLanguage: 'en', apiLanguage: 'en-us' },
]
const SUPPORT_EMAIL = 'support-transcripts@numerique.gouv.fr'
const SUPPORT_SUBJECT = 'Assistant Transcripts - Support'

type StackNavigationProp = NativeStackNavigationProp<RootStackParamList>

export default function InfoScreen() {
  const navigation = useNavigation<StackNavigationProp>()
  const insets = useInsets()
  const { t, i18n } = useTranslation()
  const { isLoggedIn, user, logout, updateUser } = useUser()
  const resetNavigationHistory = useResetNavigationHistory()
  const [isLanguagePopoverVisible, setIsLanguagePopoverVisible] =
    useState(false)

  const currentLanguage = useMemo<AppLanguage>(() => {
    return i18n.language.startsWith('fr') ? 'fr' : 'en'
  }, [i18n.language])

  const getLanguageLabel = useCallback(
    (language: AppLanguage) =>
      language === 'fr' ? t('settings.french') : t('settings.english'),
    [t]
  )

  const handleLogout = useCallback(async () => {
    await logout()
    resetNavigationHistory('Main')
  }, [logout, resetNavigationHistory])

  const handleChangeLanguage = useCallback(
    async (option: LanguageOption) => {
      setIsLanguagePopoverVisible(false)

      if (currentLanguage !== option.appLanguage) {
        await i18n.changeLanguage(option.appLanguage)
      }

      if (isLoggedIn && updateUser && user?.language !== option.apiLanguage) {
        updateUser({ language: option.apiLanguage })
      }
    },
    [currentLanguage, i18n, isLoggedIn, updateUser, user?.language]
  )

  const openLegalPath = useCallback(async (path: string) => {
    const url = `${BASE_URL}${path}`
    const isAvailable = await InAppBrowser.isAvailable()
    if (isAvailable) {
      await InAppBrowser.open(url, {
        // iOS Properties
        preferredBarTintColor: colors.secondary,
        preferredControlTintColor: 'white',
        readerMode: false,
        animated: true,
        modalPresentationStyle: 'fullScreen',
        modalTransitionStyle: 'coverVertical',
        modalEnabled: true,
        enableBarCollapsing: false,
        // Android Properties
        showTitle: false,
        toolbarColor: colors.secondary,
        secondaryToolbarColor: 'black',
        navigationBarColor: 'black',
        navigationBarDividerColor: 'white',
        enableUrlBarHiding: true,
      })
      return
    }

    await Linking.openURL(url)
  }, [])

  const handleSupportPress = useCallback(async () => {
    const screen = Dimensions.get('screen')
    const viewport = Dimensions.get('window')
    let userAgent = 'unknown'

    try {
      userAgent = await DeviceInfo.getUserAgent()
    } catch (error) {
      console.warn('Unable to read user agent for support email.', error)
    }

    const info = [
      'Info:',
      `User: ${user?.id ?? 'anonymous'}`,
      `User agent: ${userAgent}`,
      `Language: ${i18n.language}`,
      `Platform: ${Platform.OS} ${String(Platform.Version)}`,
      `Screen: ${Math.round(screen.width)}x${Math.round(screen.height)}`,
      `Viewport: ${Math.round(viewport.width)}x${Math.round(viewport.height)}`,
      `Version: ${DeviceInfo.getVersion()}`,
      `Build number: ${DeviceInfo.getBuildNumber()}`,
      `Bundle identifier: ${DeviceInfo.getBundleId()}`,
      `Device name: ${DeviceInfo.getDeviceName()}`,
      `Device model: ${DeviceInfo.getModel()}`,
      `System name: ${DeviceInfo.getSystemName()}`,
      `System version: ${DeviceInfo.getSystemVersion()}`,
      `Bundle ID: ${DeviceInfo.getBundleId()}`,
    ].join('\n')

    const query = new URLSearchParams({
      subject: SUPPORT_SUBJECT,
      body: `${t('info.supportEmailStart')}\n\n${info}`,
    }).toString()

    await Linking.openURL(`mailto:${SUPPORT_EMAIL}?${query}`)
  }, [i18n.language, t, user?.id])

  return (
    <View
      style={[
        styles.container,
        {
          paddingTop: insets.paddingTop,
          paddingBottom: insets.paddingBottom,
        },
      ]}
    >
      <View style={styles.header}>
        <Pressable
          style={({ pressed }) => [
            styles.iconButton,
            pressed && styles.iconButtonPressed,
          ]}
          onPress={() => navigation.goBack()}
          hitSlop={10}
        >
          <Lucide name="arrow-left" size={26} color={colors.primary} />
        </Pressable>
      </View>

      <ScrollView
        style={styles.content}
        contentContainerStyle={styles.contentContainer}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.brandHeader}>
          <LogoWithName />
          <AppText variant="heading">{t('info.title')}</AppText>
        </View>

        {isLoggedIn && user ? (
          <View style={styles.card}>
            <View style={styles.userBlock}>
              <AppText variant="muted" size="sm">
                {t('info.connectedAs')}
              </AppText>
              <AppText variant="bodyMedium" size="lg" numberOfLines={1}>
                {user.full_name}
              </AppText>
            </View>
            <Pressable
              style={({ pressed }) => [
                styles.rowButton,
                pressed && styles.rowButtonPressed,
              ]}
              onPress={handleLogout}
            >
              <Lucide name="log-out" size={18} color={colors.errorSecondary} />
              <AppText variant="bodyMedium" color={colors.errorSecondary}>
                {t('login.logout')}
              </AppText>
            </Pressable>
          </View>
        ) : null}

        <View style={styles.card}>
          <Popover
            isVisible={isLanguagePopoverVisible}
            arrowSize={{ width: 0, height: 0 }}
            popoverStyle={styles.popover}
            onRequestClose={() => setIsLanguagePopoverVisible(false)}
            from={
              <Pressable
                style={({ pressed }) => [
                  styles.rowButton,
                  pressed && styles.rowButtonPressed,
                ]}
                onPress={() => setIsLanguagePopoverVisible(true)}
              >
                <Lucide name="languages" size={18} color={colors.textPrimary} />
                <View style={styles.grow}>
                  <AppText variant="bodyMedium">
                    {t('settings.language')}
                  </AppText>
                  <AppText variant="muted">
                    {getLanguageLabel(currentLanguage)}
                  </AppText>
                </View>
                <Lucide
                  name="chevrons-up-down"
                  size={16}
                  color={colors.neutralTertiary}
                />
              </Pressable>
            }
          >
            <View style={styles.popoverContent}>
              {LANGUAGE_OPTIONS.map((option) => {
                const isSelected = option.appLanguage === currentLanguage

                return (
                  <Pressable
                    key={option.appLanguage}
                    style={({ pressed }) => [
                      styles.actionButton,
                      pressed && styles.rowButtonPressed,
                    ]}
                    onPress={() => void handleChangeLanguage(option)}
                  >
                    <AppText variant="body">
                      {getLanguageLabel(option.appLanguage)}
                    </AppText>
                    {isSelected ? (
                      <Lucide name="check" size={16} color={colors.primary} />
                    ) : null}
                  </Pressable>
                )
              })}
            </View>
          </Popover>

          <View style={styles.separator} />
          <Pressable
            style={({ pressed }) => [
              styles.rowButton,
              pressed && styles.rowButtonPressed,
            ]}
            onPress={() => void handleSupportPress()}
          >
            <Lucide name="life-buoy" size={18} color={colors.textPrimary} />
            <AppText variant="bodyMedium" style={styles.grow}>
              {t('info.getHelp')}
            </AppText>
            <Lucide
              name="chevron-right"
              size={16}
              color={colors.neutralTertiary}
            />
          </Pressable>
        </View>

        <View style={styles.card}>
          <View style={styles.legalBlock}>
            {LEGAL_DOCUMENTS.map((document) => {
              const urlPath = t(`info.${document.urlKey}`)

              return (
                <View key={document.labelKey}>
                  <Pressable
                    style={({ pressed }) => [
                      styles.rowButton,
                      pressed && styles.rowButtonPressed,
                    ]}
                    onPress={() => openLegalPath(urlPath)}
                  >
                    <Lucide
                      name="file-text"
                      size={18}
                      color={colors.textPrimary}
                    />
                    <AppText variant="bodyMedium" style={styles.grow}>
                      {t(`info.${document.labelKey}`)}
                    </AppText>
                    <Lucide
                      name="chevron-right"
                      size={16}
                      color={colors.neutralTertiary}
                    />
                  </Pressable>
                  {document !== LEGAL_DOCUMENTS[LEGAL_DOCUMENTS.length - 1] ? (
                    <View style={styles.separator} />
                  ) : null}
                </View>
              )
            })}
          </View>
        </View>
      </ScrollView>
    </View>
  )
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.backgroundBase,
  },
  header: {
    minHeight: 48,
    paddingHorizontal: 10,
    justifyContent: 'center',
  },
  iconButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconButtonPressed: {
    backgroundColor: colors.backgroundSubtlePressed,
  },
  content: {
    flex: 1,
    paddingHorizontal: 16,
  },
  contentContainer: {
    paddingBottom: 20,
    gap: 12,
  },
  brandHeader: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingTop: 8,
    paddingBottom: 12,
    gap: 12,
  },
  card: {
    borderRadius: 16,
    backgroundColor: colors.backgroundSubtle,
    padding: 12,
    gap: 8,
  },
  userBlock: {
    paddingHorizontal: 10,
    paddingTop: 4,
    gap: 3,
  },
  legalBlock: {
    gap: 0,
  },
  separator: {
    height: 1,
    marginHorizontal: 10,
    backgroundColor: colors.backgroundNeutralSecondary,
    opacity: 0.7,
  },
  grow: {
    flexGrow: 1,
  },
  rowButton: {
    minHeight: 44,
    borderRadius: 10,
    paddingHorizontal: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  rowButtonPressed: {
    backgroundColor: colors.backgroundSubtlePressed,
  },
  popover: {
    borderRadius: 12,
  },
  popoverContent: {
    padding: 4,
  },
  actionButton: {
    minHeight: 40,
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 8,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
  },
})
