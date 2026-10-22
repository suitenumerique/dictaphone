import { useEffect, useRef } from 'react'
import { Pressable, StyleSheet, View } from 'react-native'
import { useTranslation } from 'react-i18next'
import { useNavigation } from '@react-navigation/native'
import type { NativeStackNavigationProp } from '@react-navigation/native-stack'
import { useUploadLimit } from '@/features/files/api/uploadLimit'
import type { RootStackParamList } from '@/navigation/types'
import { unblockUploads } from '@/services/storage'
import { AppText } from './AppText'
import { colors } from './colors'

export function UploadLimitAlert({
  linkToRecordings = false,
}: {
  linkToRecordings?: boolean
}) {
  const { t } = useTranslation()
  const navigation =
    useNavigation<NativeStackNavigationProp<RootStackParamList>>()
  const { data } = useUploadLimit()
  const isFull = data
    ? data.limit !== null && data.count >= data.limit
    : undefined

  // Quota rejections block uploads as "permission": retry them once the user
  // has freed a slot. Only on that transition, so a genuine 403 is not retried
  // on every refetch.
  const wasFull = useRef(isFull)
  useEffect(() => {
    if (wasFull.current && isFull === false) unblockUploads(['permission'])
    if (isFull !== undefined) wasFull.current = isFull
  }, [isFull])

  if (!data || !isFull) return null

  return (
    <View accessibilityRole="alert" style={styles.container}>
      <AppText variant="bodyBold">{t('recordings.fileLimit.title')}</AppText>
      <AppText>
        {t('recordings.fileLimit.description', { limit: data.limit })}
      </AppText>
      {linkToRecordings && (
        <Pressable
          accessibilityRole="link"
          onPress={() => navigation.navigate('Main')}
        >
          <AppText color={colors.primary}>
            {t('recordings.fileLimit.manageRecordings')}
          </AppText>
        </Pressable>
      )}
    </View>
  )
}

const styles = StyleSheet.create({
  container: {
    alignSelf: 'stretch',
    backgroundColor: colors.warningSurface,
    borderColor: colors.warningBorder,
    borderWidth: 1,
    borderRadius: 8,
    margin: 12,
    padding: 12,
    gap: 8,
  },
})
