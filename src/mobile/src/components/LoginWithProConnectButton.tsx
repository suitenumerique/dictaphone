import { Pressable, StyleSheet, View } from 'react-native'
// @ts-expect-error SVG
import ProConnectContent from '../assets/proconnect-content.svg'
import { login } from '@/services/authService'
import { colors } from './colors'

export function LoginWithProConnectButton() {
  return (
    <View style={styles.container}>
      <Pressable onPress={() => login()} style={styles.button}>
        <ProConnectContent />
      </Pressable>
    </View>
  )
}

const styles = StyleSheet.create({
  container: {
    display: 'flex',
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 8,
  },
  button: {
    backgroundColor: colors.primary,
    paddingLeft: 8,
    paddingRight: 8,
    paddingTop: 4,
    paddingBottom: 4,
    borderRadius: 8,
  },
})
