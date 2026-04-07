// src/screens/LoginScreen.tsx
import React from 'react';
import { Button, View, StyleSheet } from 'react-native';
import { useTranslation } from 'react-i18next';
import { login } from '../services/authService';

type LoginScreenProps = {
  navigation: {
    replace: (routeName: string) => void;
  };
};

export default function LoginScreen({ navigation }: LoginScreenProps) {
  const { t } = useTranslation();

  async function handleLogin(): Promise<void> {
    try {
      await login();
      navigation.replace('Home');
    } catch (error) {
      console.error('Login failed:', error);
    }
  }

  return (
    <View style={styles.container}>
      <Button title={t('recordings.loginButton')} onPress={handleLogin} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
});
