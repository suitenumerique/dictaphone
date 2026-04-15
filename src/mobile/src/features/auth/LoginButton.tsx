import { Pressable, StyleSheet, Text } from 'react-native';
import React, { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { login } from '../../services/authService';

export function LoginButton() {
  const { t } = useTranslation();

  const handleLogin = useCallback(async () => {
    try {
      await login();
    } catch (error) {
      console.error('Login failed:', error);
    }
  }, []);

  return (
    <Pressable
      style={({ pressed }) => [
        styles.loginButton,
        pressed && styles.loginButtonPressed,
      ]}
      onPress={handleLogin}
    >
      <Text style={styles.loginButtonText}>{t('login.loginCta')}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  loginButton: {
    width: '100%',
    backgroundColor: '#3E5DE7',
    borderRadius: 4,
    height: 40,
    paddingVertical: 0,
    display: 'flex',
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
  },
  loginButtonPressed: {
    backgroundColor: '#5771e7',
  },
  loginButtonText: {
    color: '#FFFFFF',
    fontSize: 18,
    fontWeight: 400,
    textAlign: 'center',
  },
});
