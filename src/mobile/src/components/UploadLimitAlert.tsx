import { Pressable, StyleSheet, View } from 'react-native'
import { useTranslation } from 'react-i18next'
import { useNavigation } from '@react-navigation/native'
import type { NativeStackNavigationProp } from '@react-navigation/native-stack'
import { useUploadLimit } from '@/features/files/api/uploadLimit'
import type { RootStackParamList } from '@/navigation/types'
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
  if (!data || data.limit === null || data.count < data.limit) return null

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
