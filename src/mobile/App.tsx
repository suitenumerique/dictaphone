import './src/i18n/index';
import React, { useEffect } from 'react';
import { StatusBar } from 'react-native';
import {
  NavigationContainer,
  RouteProp,
  useRoute,
} from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import RecordingScreen from '@/screens/RecordingScreen';
import RecordingsScreen from './src/screens/RecordingsScreen';
import { storeCsrfToken, storeSessionCookie } from './src/services/authService';
import { queryClient } from '@/api/queryClient';
import { QueryClientProvider } from '@tanstack/react-query';
import BootSplash from 'react-native-bootsplash';
import LoginScreen from '@/screens/LoginScreen';
import RecordingDetailsScreen from '@/screens/RecordingDetailsScreen';
import type { RootStackParamList } from '@/navigation/types';
import { useResetNavigationHistory } from '@/navigation/useRestNavigationHistory';

const RootStack = createNativeStackNavigator<RootStackParamList>();

type AuthCallbackRoute = RouteProp<RootStackParamList, 'AuthCallback'>;

function AuthCallbackScreen() {
  const route = useRoute<AuthCallbackRoute>();
  const resetNavigationHistory = useResetNavigationHistory();

  useEffect(() => {
    if (route.params.sessionId && route.params.csrfToken) {
      Promise.all([
        storeSessionCookie(route.params.sessionId),
        storeCsrfToken(route.params.csrfToken),
      ])
        .then(() => {
          queryClient.invalidateQueries();
        })
        .catch(e =>
          console.error('Failed to store session cookie and csrf token:', e),
        );
    }
    resetNavigationHistory('Main');
  }, [resetNavigationHistory, route.params]);

  return null;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <StatusBar barStyle="dark-content" />
      <NavigationContainer
        onReady={() => {
          BootSplash.hide();
        }}
        linking={{
          prefixes: ['assistant-transcripts://'],
          config: {
            screens: {
              Login: 'login',
              Main: 'record',
              RecordingInProgress: 'recording',
              AuthCallback: 'auth/callback',
            },
          },
        }}
        fallback={<></>}
      >
        <RootStack.Navigator screenOptions={{ headerShown: false }}>
          <RootStack.Screen name="Login" component={LoginScreen} />
          <RootStack.Screen name="Main" component={RecordingsScreen} />
          <RootStack.Screen
            name="RecordingInProgress"
            component={RecordingScreen}
            options={{ gestureEnabled: false }}
          />
          <RootStack.Screen
            name="RecordingDetails"
            component={RecordingDetailsScreen}
          />
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
