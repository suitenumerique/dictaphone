import React from 'react'
import { Pressable, StyleSheet, View } from 'react-native'
import { Lucide } from '@react-native-vector-icons/lucide'
import type { TFunction } from 'i18next'
import MainMenu from '@/components/MainMenu'
import { LoginButton } from '@/components/LoginButton'
import { AppText } from '@/components/AppText'
import { colors } from '@/components/colors'
// @ts-expect-error Icon
import LogoWithName from '@/assets/logo-with-name.svg'

type RecordingsTopBarProps = {
  isOnline: boolean
  isLoading: boolean
  isLoggedIn: boolean
  showWifiOnlyCard: boolean
  onSyncNow: () => void
  t: TFunction
}

export function RecordingsTopBar({
  isOnline,
  isLoading,
  isLoggedIn,
  showWifiOnlyCard,
  onSyncNow,
  t,
}: RecordingsTopBarProps) {
  return (
    <View style={styles.topBar}>
      <View style={styles.topBarHeader}>
        <LogoWithName style={styles.title} />
        <MainMenu />
      </View>
      {isOnline && !isLoading && !isLoggedIn && (
        <View style={styles.loginCard}>
          <AppText variant="body" align="center" color={colors.neutralTertiary}>
            {t('recordings.loginHelper')}
          </AppText>
          <LoginButton />
        </View>
      )}
      {!isOnline && (
        <View style={[styles.networkCard, styles.offlineCard]}>
          <Lucide name="wifi-off" size={16} color={colors.warning} />
          <AppText variant="body" color={colors.warning}>
            {t('recordings.offline')}
          </AppText>
        </View>
      )}
      {showWifiOnlyCard && (
        <View style={[styles.networkCard, styles.wifiOnlyCard]}>
          <Lucide name="wifi-off" size={16} color={colors.warning} />
          <AppText
            variant="body"
            color={colors.warning}
            style={styles.wifiOnlyCardText}
          >
            {t('recordings.wifiOnlySync')}
          </AppText>
          <Pressable
            onPress={onSyncNow}
            style={({ pressed }) => [
              styles.wifiOnlySyncButton,
              pressed && styles.wifiOnlySyncButtonPressed,
            ]}
          >
            <Lucide
              name="cloud-upload"
              size={22}
              color={colors.neutralSecondary}
            />
          </Pressable>
        </View>
      )}
    </View>
  )
}

const styles = StyleSheet.create({
  topBar: {
    paddingHorizontal: 16,
    paddingTop: 4,
    paddingBottom: 10,
    gap: 12,
  },
  topBarHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingRight: 8,
  },
  title: {
    marginBottom: 2,
  },
  loginCard: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 8,
    padding: 12,
    borderRadius: 8,
    backgroundColor: colors.backgroundBase,
    borderWidth: 1,
    borderColor: colors.surfacePrimary,
    boxShadow: [
      {
        blurRadius: 15,
        spreadDistance: 5,
        color: colors.shadowDefault,
        offsetX: 0,
        offsetY: 0,
      },
    ],
  },
  networkCard: {
    borderRadius: 10,
    paddingVertical: 12,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: 1,
  },
  offlineCard: {
    backgroundColor: colors.warningSurface,
    borderColor: colors.warningBorder,
  },
  wifiOnlyCard: {
    backgroundColor: colors.warningSurface,
    borderColor: colors.warningBorder,
    paddingVertical: 8,
  },
  wifiOnlyCardText: {
    flex: 1,
  },
  wifiOnlySyncButton: {
    display: 'flex',
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    borderColor: colors.warningBorder,
    borderWidth: 1,
    backgroundColor: colors.backgroundSubtle,
  },
  wifiOnlySyncButtonPressed: {
    backgroundColor: colors.backgroundSubtlePressed,
  },
})
