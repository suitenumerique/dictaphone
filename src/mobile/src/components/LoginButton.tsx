import { Pressable, StyleSheet } from 'react-native';
import React, { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { login } from '@/services/authService';
import { AppText } from './AppText';
import { colors } from '@/components/colors';

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
      <AppText variant="button">{t('login.loginCta')}</AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  loginButton: {
    width: '100%',
    backgroundColor: colors.primary,
    borderRadius: 4,
    height: 40,
    paddingVertical: 0,
    display: 'flex',
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
  },
  loginButtonPressed: {
    backgroundColor: colors.primaryPressed,
  },
});
