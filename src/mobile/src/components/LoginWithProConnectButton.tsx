import { Pressable, StyleSheet, View } from 'react-native';
// @ts-ignore
import ProConnectContent from '../assets/proconnect-content.svg';
import { login } from '../services/authService';

export function LoginWithProConnectButton() {
  return (
    <View style={styles.container}>
      <Pressable onPress={() => login()} style={styles.button}>
        <ProConnectContent/>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    display: "flex",
    flexDirection: "row",
    justifyContent: "center",
    alignItems: "center",
    gap: 8,
  },
  button: {
    backgroundColor: '#3e5de7',
    paddingLeft: 8,
    paddingRight: 8,
    paddingTop: 4,
    paddingBottom: 4,
    borderRadius: 8,
  },
});
