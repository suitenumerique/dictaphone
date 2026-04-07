import React, { useEffect } from 'react';
import { StatusBar } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { useTranslation } from 'react-i18next';
import i18n from './src/i18n';
import HomeScreen from './src/screens/HomeScreen';
import RecordingsScreen from './src/screens/RecordingsScreen';
import SettingsScreen from './src/screens/SettingsScreen';
import { getSettings } from './src/services/storage';
import { Lucide } from '@react-native-vector-icons/lucide';
import { createNativeBottomTabNavigator } from '@react-navigation/bottom-tabs/unstable';
import { TrackPlayer } from 'react-native-nitro-player';

const Tabs = createNativeBottomTabNavigator();

function App() {
  const { t } = useTranslation();

  useEffect(() => {
    TrackPlayer.configure({
      androidAutoEnabled: true,
      carPlayEnabled: true,
      showInNotification: true,
      lookaheadCount: 1,
    });
  }, []);

  useEffect(() => {
    const settings = getSettings();
    i18n.changeLanguage(settings.language).catch(() => undefined);
  }, []);

  return (
    <>
      <StatusBar barStyle="dark-content" />
      <NavigationContainer>
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
      </NavigationContainer>
    </>
  );
}

export default App;
