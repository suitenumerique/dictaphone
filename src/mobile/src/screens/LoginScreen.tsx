// src/screens/LoginScreen.tsx
import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '@/services/storage';
// @ts-ignore
import LogoWithName from '../assets/logo-single-line.svg';
import { LoginButton } from '@/components/LoginButton';
import { useInsets } from '@/utils/useInsets';
import { AppText } from '@/components/AppText';
import { colors } from '@/components/colors';

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
          <AppText variant="subtitle" size="md" align="center">
            {t('login.subtitle')}
          </AppText>
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
    backgroundColor: colors.backgroundBase,
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
});
