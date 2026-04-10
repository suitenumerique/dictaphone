import React, { useEffect } from 'react';
import { StatusBar, Text, View } from 'react-native';
import {
  NavigationContainer,
  RouteProp,
  useRoute,
} from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useTranslation } from 'react-i18next';
import i18n from './src/i18n';
import HomeScreen from './src/screens/HomeScreen';
import RecordingsScreen from './src/screens/RecordingsScreen';
import SettingsScreen from './src/screens/SettingsScreen';
import { getSettings } from './src/services/storage';
import { Lucide } from '@react-native-vector-icons/lucide';
import { createNativeBottomTabNavigator } from '@react-navigation/bottom-tabs/unstable';
import { storeCsrfToken, storeSessionCookie } from './src/services/authService';
import { useNavigation } from '@react-navigation/core';
import { queryClient } from '@/api/queryClient';
import { QueryClientProvider } from '@tanstack/react-query';
import BootSplash from 'react-native-bootsplash';

const Tabs = createNativeBottomTabNavigator();
const RootStack = createNativeStackNavigator();

type AuthCallbackRoute = RouteProp<
  Record<string, { [key: string]: string | undefined }>,
  'AuthCallback'
>;

function AuthCallbackScreen() {
  const route = useRoute<AuthCallbackRoute>();
  const navigation = useNavigation();

  useEffect(() => {
    if (route.params["$sessionId"] && route.params.csrfToken) {
      Promise.all([
        storeSessionCookie(route.params['$sessionId']),
        storeCsrfToken(route.params.csrfToken),
      ])
        .then(() => queryClient.invalidateQueries())
        .catch(e =>
          console.error('Failed to store session cookie and csrf token:', e),
        );
    }
    navigation.navigate('MainTabs' as never);
  }, [navigation, route.params]);

  return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
      <Text>Auth callback received</Text>
    </View>
  );
}

function MainTabs() {
  const { t } = useTranslation();

  return (
    <Tabs.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: '#111827',
        tabBarInactiveTintColor: '#9CA3AF',
        tabBarLabelStyle: {
          fontSize: 12,
          fontWeight: '600',
        },
      }}
    >
      <Tabs.Screen
        name="Record"
        component={HomeScreen}
        options={{
          tabBarLabel: t('tabs.record'),
          tabBarIcon: ({ focused }) => ({
            type: 'image',
            source: Lucide.getImageSourceSync(
              'mic',
              24,
              focused ? '#111827' : '#9CA3AF',
            ),
          }),
        }}
      />
      <Tabs.Screen
        name="Recordings"
        component={RecordingsScreen}
        options={{
          tabBarLabel: t('tabs.recordings'),
          tabBarIcon: ({ focused }) => ({
            type: 'image',
            source: Lucide.getImageSourceSync(
              'list-music',
              24,
              focused ? '#111827' : '#9CA3AF',
            ),
          }),
        }}
      />
      <Tabs.Screen
        name="Settings"
        component={SettingsScreen}
        options={{
          tabBarLabel: t('tabs.settings'),
          tabBarIcon: ({ focused }) => ({
            type: 'image',
            source: Lucide.getImageSourceSync(
              'settings',
              24,
              focused ? '#111827' : '#9CA3AF',
            ),
          }),
        }}
      />
    </Tabs.Navigator>
  );
}

function App() {
  useEffect(() => {
    const settings = getSettings();
    i18n.changeLanguage(settings.language).catch(() => undefined);
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <StatusBar barStyle="dark-content" />
      <NavigationContainer
        onReady={() => {
          BootSplash.hide();
        }}
        linking={{
          prefixes: ['lasuite-dictaphone://'],
          config: {
            screens: {
              MainTabs: 'record',
              AuthCallback: 'auth/callback',
            },
          },
        }}
        fallback={<></>}
      >
        <RootStack.Navigator screenOptions={{ headerShown: false }}>
          <RootStack.Screen name="MainTabs" component={MainTabs} />
          <RootStack.Screen
            name="AuthCallback"
            component={AuthCallbackScreen}
          />
        </RootStack.Navigator>
      </NavigationContainer>
    </QueryClientProvider>
  );
}

export default App;
