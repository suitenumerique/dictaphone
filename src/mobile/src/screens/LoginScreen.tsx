// src/screens/LoginScreen.tsx
import React, { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '@/services/storage';
// @ts-ignore
import LogoWithName from '../assets/logo-single-line.svg';
import { LoginButton } from '@/features/auth/LoginButton';
import { useInsets } from '@/utils/useInsets';

type LoginScreenProps = {
  navigation: {
    replace: (routeName: string) => void;
  };
};

export default function LoginScreen({ navigation }: LoginScreenProps) {
  const { t } = useTranslation();

  const { user } = useUserStore();
  const insets = useInsets();

  useEffect(() => {
    if (user) {
      navigation.replace('Main');
    }
  }, [user, navigation]);

  if (user) {
    return null;
  }

  return (
    <View style={[insets]}>
      <View style={styles.container}>
        <View style={styles.infoContainer}>
          <LogoWithName />
          <Text style={styles.subtitle}>{t('login.subtitle')}</Text>
        </View>
        <LoginButton />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
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
