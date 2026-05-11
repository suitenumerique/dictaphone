import React, { useEffect } from 'react'
import { StyleSheet, View } from 'react-native'
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated'
import { colors } from '@/components/colors'
import { AppText } from '@/components/AppText'
import { useTranslation } from 'react-i18next'

type Props = {
  uploadedBytes: number
  totalBytes: number
}

export default function UploadProgress({ totalBytes, uploadedBytes }: Props) {
  const { t } = useTranslation()
  const width = useSharedValue(0)

  const progressPercentage = totalBytes > 0 ? (uploadedBytes / totalBytes) * 100 : 0

  useEffect(() => {
    width.value = withTiming(progressPercentage, {
      duration: 350,
    })
  }, [progressPercentage, width])

  const progressStyle = useAnimatedStyle(() => {
    return {
      width: `${width.value}%`,
    }
  })

  return (
    <View style={styles.container}>
      {/* PROGRESS BAR */}
      <View style={styles.progressBackground}>
        <Animated.View style={[styles.progressFill, progressStyle]} />
      </View>

      {/* FOOTER */}
      <View style={styles.footer}>
        <AppText variant="muted">
          {t('shared.utils.fileSizeMb', {
            size: uploadedBytes / (1024 * 1024),
          })}
          {' / '}
          {t('shared.utils.fileSizeMb', { size: totalBytes / (1024 * 1024) })}
        </AppText>
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  container: {},

  progressBackground: {
    height: 12,
    backgroundColor: colors.secondary,
    borderRadius: 999,
    overflow: 'hidden',
    marginTop: 4,
  },

  progressFill: {
    height: '100%',
    borderRadius: 999,
    backgroundColor: colors.primary,
  },

  footer: {
    marginTop: 4,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
})
