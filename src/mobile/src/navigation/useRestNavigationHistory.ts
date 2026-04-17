import { useNavigation } from '@react-navigation/core'
import type { NativeStackNavigationProp } from '@react-navigation/native-stack'
import type { RootStackParamList } from '@/navigation/types'
import { useCallback } from 'react'

export function useResetNavigationHistory() {
  const navigation =
    useNavigation<NativeStackNavigationProp<RootStackParamList>>()

  return useCallback(
    (name: keyof RootStackParamList) =>
      navigation.reset({
        index: 0,
        routes: [{ name: name }],
      }),
    [navigation]
  )
}
