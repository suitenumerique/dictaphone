import {
  Linking,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  View,
} from 'react-native'
import React, { useMemo, useState } from 'react'
import { AppText } from '@/components/AppText'
import { useTranslation } from 'react-i18next'
import { useConfig } from '@/api/useConfig'
import { colors } from '@/components/colors'
import { lt } from 'semver'
import DeviceInfo from 'react-native-device-info'
type UpdateRequirement = 'none' | 'optional' | 'mandatory'

const currentVersion = DeviceInfo.getVersion()

export function UpdateModal() {
  const { t } = useTranslation()
  const configQuery = useConfig()
  const [dismissOptionalUpdate, setDismissOptionalUpdate] = useState(false)
  const storeUrls = useMemo(
    () => ({
      ios: configQuery.data?.mobile_app?.ios_download_link,
      android: configQuery.data?.mobile_app?.android_download_link,
    }),
    [
      configQuery.data?.mobile_app?.android_download_link,
      configQuery.data?.mobile_app?.ios_download_link,
    ]
  )
  const updateRequirement = useMemo<UpdateRequirement>(() => {
    const mobileAppsConfig = configQuery.data?.mobile_app
    if (!mobileAppsConfig) {
      return 'none'
    }

    const latestVersion =
      Platform.OS === 'ios'
        ? mobileAppsConfig.ios_version
        : mobileAppsConfig.android_version

    const minimumVersion =
      Platform.OS === 'ios'
        ? mobileAppsConfig.ios_min_version
        : mobileAppsConfig.android_min_version

    if (!latestVersion || !minimumVersion) {
      return 'none'
    }

    if (lt(currentVersion, minimumVersion)) {
      return 'mandatory'
    }
    if (lt(currentVersion, latestVersion)) {
      return 'optional'
    }
    return 'none'
  }, [configQuery.data])
  const showUpdateModal =
    updateRequirement === 'mandatory' ||
    (updateRequirement === 'optional' && !dismissOptionalUpdate)

  const openStore = () => {
    const url = Platform.OS === 'ios' ? storeUrls.ios : storeUrls.android
    if (url) {
      Linking.openURL(url)
    }
  }

  return (
    <Modal
      visible={showUpdateModal}
      transparent
      animationType="fade"
      onRequestClose={() => {
        if (updateRequirement === 'optional') {
          setDismissOptionalUpdate(true)
        }
      }}
    >
      <View style={styles.modalBackdrop}>
        <View style={styles.modalCard}>
          <AppText variant="heading" align="center">
            {t('update.title')}
          </AppText>
          <AppText
            variant="body"
            align="center"
            style={styles.modalDescription}
          >
            {updateRequirement === 'mandatory'
              ? t('update.descriptionMandatory')
              : t('update.descriptionOptional')}
          </AppText>
          <View style={styles.modalActions}>
            {updateRequirement === 'optional' ? (
              <Pressable
                onPress={() => setDismissOptionalUpdate(true)}
                style={({ pressed }) => [
                  styles.secondaryButton,
                  pressed && styles.secondaryButtonPressed,
                ]}
              >
                <AppText variant="bodyMedium" align="center">
                  {t('update.later')}
                </AppText>
              </Pressable>
            ) : null}
            <Pressable
              onPress={openStore}
              style={({ pressed }) => [
                styles.primaryButton,
                pressed && styles.primaryButtonPressed,
              ]}
            >
              <AppText variant="button" align="center">
                {t('update.now')}
              </AppText>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  )
}

const styles = StyleSheet.create({
  modalBackdrop: {
    flex: 1,
    backgroundColor: colors.overlayBackdrop,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 24,
  },
  modalCard: {
    width: '100%',
    borderRadius: 16,
    backgroundColor: colors.backgroundBase,
    paddingHorizontal: 20,
    paddingVertical: 20,
    gap: 12,
  },
  modalDescription: {
    color: colors.textSecondary,
  },
  modalActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    alignItems: 'center',
    gap: 8,
    marginTop: 4,
  },
  primaryButton: {
    minHeight: 42,
    borderRadius: 12,
    backgroundColor: colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 16,
  },
  primaryButtonPressed: {
    backgroundColor: colors.primaryPressed,
  },
  secondaryButton: {
    minHeight: 42,
    borderRadius: 12,
    backgroundColor: colors.backgroundNeutralSecondary,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 16,
  },
  secondaryButtonPressed: {
    backgroundColor: colors.backgroundNeutralSecondaryPressed,
  },
})
