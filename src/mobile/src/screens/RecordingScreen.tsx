import React from 'react'
import { StyleSheet, View } from 'react-native'
import { AudioRecorder } from '@/components/AudioRecorder'
import { useInsets } from '@/utils/useInsets'

export default function RecordScreen() {
  const insets = useInsets()

  return (
    <View style={[styles.container, insets]}>
      <View style={styles.recorderContainer}>
        <AudioRecorder />
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  container: {
    justifyContent: 'flex-start',
    alignItems: 'center',
  },
  recorderContainer: {
    flex: 1,
    width: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 20,
  },
})
