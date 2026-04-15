import React, { useCallback, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import Popover from 'react-native-popover-view';
import { Lucide } from '@react-native-vector-icons/lucide';
import { useUser } from '@/features/auth/api/useUser';
import { useTranslation } from 'react-i18next';

export default function MainMenu() {
  const [isPopoverVisible, setIsPopoverVisible] = useState(false);
  const { logout, isLoggedIn } = useUser();
  const {t} = useTranslation();

  const handleLogout = useCallback(() => {
    setIsPopoverVisible(false);
    logout();
  }, [logout]);

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
          <Pressable onPress={() => setIsPopoverVisible(true)}>
            <Lucide size={24} name="ellipsis" color={'#3E5DE7'} />
          </Pressable>
        }
      >
        <View style={styles.popoverContent}>
          <Pressable style={styles.logoutButton} onPress={handleLogout}>
            <Lucide name="log-out" size={15} color="#222631" />
            <Text style={styles.logoutText}>{t("login.logout")}</Text>
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
  button: {
    paddingVertical: 12,
    paddingHorizontal: 16,
    backgroundColor: '#007AFF',
    borderRadius: 8,
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
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
  logoutText: {
    color: '#222631',
    fontWeight: '600',
  },
});
