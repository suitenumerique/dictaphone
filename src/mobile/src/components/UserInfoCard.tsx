import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { useUser } from '@/features/auth/api/useUser';
import { LoginWithProConnectButton } from './LoginWithProConnectButton';
import { Lucide } from '@react-native-vector-icons/lucide';

export function UserInfoCard() {
  const { isLoading, isLoggedIn, user, logout } = useUser();

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="small" color="#1D4ED8" />
      </View>
    );
  }

  if (!isLoggedIn || !user) {
    return <LoginWithProConnectButton />;
  }

  return (
    <View style={styles.card}>
      <View style={styles.info}>
        <View style={styles.firstLine}>
          <Text style={styles.name}>
            {user.full_name || user.last_name || 'User'}
          </Text>

          <Pressable style={styles.logoutButton} onPress={logout}>
            <Lucide name="log-out" size={15} color="#1D4ED8" />
          </Pressable>
        </View>

        <Text style={styles.email}>{user.email}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 14,
    gap: 10,
    borderWidth: 1,
    borderColor: '#E5E7EB',
  },
  info: {
    flexDirection: 'column',
    display: 'flex',
    gap: 4,
  },
  firstLine: {
    display: "flex",
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  name: {
    fontSize: 16,
    fontWeight: '700',
    color: '#111827',
  },
  email: {
    fontSize: 14,
    color: '#4B5563',
  },
  logoutButton: {
      width: 32,
      height: 32,
      borderRadius: 16,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: '#EFF6FF',
  },
  logoutText: {
    color: '#FFFFFF',
    fontWeight: '700',
    fontSize: 13,
  },
  loadingContainer: {
    paddingVertical: 16,
    alignItems: 'center',
  },
});
