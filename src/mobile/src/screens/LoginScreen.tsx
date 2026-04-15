// src/screens/LoginScreen.tsx
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { login } from '../services/authService';
import { useUserStore } from '@/services/storage';
import { SafeAreaView } from 'react-native-screens/experimental';
// @ts-ignore
import LogoWithName from '../assets/logo-single-line.svg';

type LoginScreenProps = {
  navigation: {
    replace: (routeName: string) => void;
  };
};

export default function LoginScreen({ navigation }: LoginScreenProps) {
  const { t } = useTranslation();

  const { user } = useUserStore();

  async function handleLogin(): Promise<void> {
    try {
      await login();
    } catch (error) {
      console.error('Login failed:', error);
    }
  }

  if (user) {
    navigation.replace('Main');
    return null;
  }

  return (
    <SafeAreaView edges={{ bottom: true, top: true }} style={styles.safeArea}>
      <View style={styles.container}>
        <View style={styles.infoContainer}>
            <LogoWithName />
          <Text style={styles.subtitle}>{t('login.subtitle')}</Text>
        </View>
        <Pressable style={styles.loginButton} onPress={handleLogin}>
          <Text style={styles.loginButtonText}>{t('login.loginCta')}</Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    backgroundColor: '#ffffff',
    flex: 1,
  },
  container: {
    display: 'flex',
    height: '100%',
    flexDirection: 'column',
    paddingVertical: 30,
    paddingHorizontal: 10,
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#ffffff',
  },
  infoContainer: {
    flexGrow: 1,
    marginHorizontal: 10,
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 10,
  },
  subtitle: {
    textAlign: 'center',
    fontSize: 12,
    color: '#626A80',
  },
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
    maxWidth: 300,
  },
  loginButtonText: {
    color: '#FFFFFF',
    fontSize: 18,
    fontWeight: 400,
    textAlign: 'center',
  },
});
