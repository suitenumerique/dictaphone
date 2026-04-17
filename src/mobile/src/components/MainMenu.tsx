import React, { useCallback, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Popover from 'react-native-popover-view';
import { Lucide } from '@react-native-vector-icons/lucide';
import { useUser } from '@/features/auth/api/useUser';
import { useTranslation } from 'react-i18next';
import { AppText } from './AppText';
import { colors } from './colors';
import { useResetNavigationHistory } from '@/navigation/useRestNavigationHistory';

export default function MainMenu() {
  const [isPopoverVisible, setIsPopoverVisible] = useState(false);
  const { logout, isLoggedIn } = useUser();
  const { t } = useTranslation();
  const resetNavigationHistory = useResetNavigationHistory();

  const handleLogout = useCallback(async () => {
    setIsPopoverVisible(false);
    await logout();
    resetNavigationHistory('Main');
  }, [logout, resetNavigationHistory]);

  if (!isLoggedIn) {
    return null;
  }

  return (
    <View style={styles.container}>
      <Popover
        isVisible={isPopoverVisible}
        arrowSize={{ width: 0, height: 0 }}
        popoverStyle={styles.popover}
        onRequestClose={() => setIsPopoverVisible(false)}
        from={
          <Pressable
            onPress={() => setIsPopoverVisible(true)}
            style={({ pressed }) => [
              styles.iconButton,
              pressed && styles.iconButtonPressed,
            ]}
          >
            <Lucide size={24} name="ellipsis" color={colors.primary} />
          </Pressable>
        }
      >
        <View style={styles.popoverContent}>
          <Pressable style={styles.logoutButton} onPress={handleLogout}>
            <Lucide name="log-out" size={15} color={colors.textPrimary} />
            <AppText
              variant="body"
              color={colors.textPrimary}
              style={styles.fixMarginBottom}
            >
              {t('login.logout')}
            </AppText>
          </Pressable>
        </View>
      </Popover>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    justifyContent: 'center',
    alignItems: 'flex-end',
  },
  iconButton: {
    display: 'flex',
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconButtonPressed: {
    backgroundColor: colors.backgroundSubtlePressed,
  },
  fixMarginBottom: {
    marginTop: -3,
  },
  popover: { borderRadius: 12 },
  popoverContent: {
    padding: 4,
  },
  logoutButton: {
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 8,
    display: 'flex',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    justifyContent: 'center',
  },
});
