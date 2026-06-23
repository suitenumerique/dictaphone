import { useEffect, useRef } from 'react'
import { Alert, Platform } from 'react-native'
import { useTranslation } from 'react-i18next'
import { useSettingsStore } from '@/services/storage'

export function CheckBatteryOptimization() {
  const { t } = useTranslation()
  const hasHydrated = useSettingsStore((state) => state.hasHydrated)
  const androidBatteryWarningShown = useSettingsStore(
    (state) => state.androidBatteryWarningShown
  )
  const setAndroidBatteryWarningShown = useSettingsStore(
    (state) => state.setAndroidBatteryWarningShown
  )
  const checksRun = useRef<boolean>(false)

  useEffect(() => {
    if (checksRun.current) return
    if (!hasHydrated) return
    checksRun.current = true

    if (Platform.OS !== 'android') return
    if (androidBatteryWarningShown) return

    Alert.alert(
      t('home.batteryRestrictionsTitle'),
      t('home.batteryOptimizationMessage'),
      [
        {
          text: t('home.doNotShowAgain'),
          onPress: () => setAndroidBatteryWarningShown(true),
        },
      ],
      { cancelable: false }
    )
  }, [
    androidBatteryWarningShown,
    hasHydrated,
    setAndroidBatteryWarningShown,
    t,
  ])

  return null
}
