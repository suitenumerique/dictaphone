import './src/i18n/index'
import React, { useEffect } from 'react'
import { Alert, AppState, StatusBar } from 'react-native'
import {
  NavigationContainer,
  RouteProp,
  useRoute,
} from '@react-navigation/native'
import { createNativeStackNavigator } from '@react-navigation/native-stack'
import RecordingScreen from '@/screens/RecordingScreen'
import RecordingsScreen from './src/screens/RecordingsScreen'
import {
  clearAuthState,
  exchangeCodeForTokens,
} from '@/services/authService'
import { queryClient } from '@/api/queryClient'
import { QueryClientProvider } from '@tanstack/react-query'
import BootSplash from 'react-native-bootsplash'
import LoginScreen from '@/screens/LoginScreen'
import RecordingDetailsScreen from '@/screens/RecordingDetailsScreen'
import InfoScreen from '@/screens/InfoScreen'
import type { RootStackParamList } from '@/navigation/types'
import { useResetNavigationHistory } from '@/navigation/useRestNavigationHistory'
import { GestureHandlerRootView } from 'react-native-gesture-handler'
import { AppInitialization } from '@/components/AppInitialization'
import { logPosthogScreenChange } from '@/features/analytics/hooks/useAnalytics'
import { UpdateModal } from '@/features/config/UpdateModal'
import { useRecordingsStore } from '@/services/storage'
import { useTranslation } from 'react-i18next'
import { CheckBatteryOptimization } from '@/components/CheckBatteryOptimization'

const RootStack = createNativeStackNavigator<RootStackParamList>()

type AuthCallbackRoute = RouteProp<RootStackParamList, 'AuthCallback'>

function AuthCallbackScreen() {
  const route = useRoute<AuthCallbackRoute>()
  const resetNavigationHistory = useResetNavigationHistory()
  const codeRef = React.useRef<string | null>(null)

  useEffect(() => {
    const params = route.params ?? {}

    if (params.logout) {
      void clearAuthState()
      resetNavigationHistory('Login')
      return
    }

    if (!params.code || !params.state) {
      console.error('OAuth callback is missing authorization code or state')
      void clearAuthState()
      resetNavigationHistory('Login')
      return
    }

    if (codeRef.current === params.code) {
      return
    }
    codeRef.current = params.code

    exchangeCodeForTokens(codeRef.current, params.state)
      .then(() => queryClient.invalidateQueries())
      .then(() => resetNavigationHistory('Main'))
      .catch((e) => {
        console.error('Failed to exchange authorization code for tokens:', e)
        clearAuthState()
          .catch((clearError) =>
            console.error('Failed to clear auth state:', clearError)
          )
          .finally(() => resetNavigationHistory('Login'))
      })
  }, [resetNavigationHistory, route.params])

  return null
}

function MissingFilesAlertHandler() {
  const { t } = useTranslation()
  const missingFilesPending = useRecordingsStore(
    (state) => state.missingFilesPending
  )
  const clearMissingFilesPending = useRecordingsStore(
    (state) => state.clearMissingFilesPending
  )
  const appStateRef = React.useRef(AppState.currentState)

  const showMissingFilesAlertIfPossible = React.useCallback(() => {
    if (appStateRef.current !== 'active' || !missingFilesPending) {
      return
    }

    Alert.alert(
      t('recordings.missingFiles.title'),
      t('recordings.missingFiles.message', { files: missingFilesPending })
    )
    clearMissingFilesPending()
  }, [clearMissingFilesPending, missingFilesPending, t])

  useEffect(() => {
    const subscription = AppState.addEventListener('change', (nextState) => {
      appStateRef.current = nextState
      if (nextState === 'active') {
        showMissingFilesAlertIfPossible()
      }
    })
    return () => subscription.remove()
  }, [showMissingFilesAlertIfPossible])

  useEffect(() => {
    showMissingFilesAlertIfPossible()
  }, [showMissingFilesAlertIfPossible])

  return null
}

function App() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <QueryClientProvider client={queryClient}>
        <AppInitialization>
          <MissingFilesAlertHandler />
          <CheckBatteryOptimization />
          <StatusBar barStyle="dark-content" />
          <NavigationContainer
            onReady={() => {
              BootSplash.hide()
            }}
            linking={{
              prefixes: ['fr-gouv-assistant-transcripts://'],
              config: {
                screens: {
                  Login: 'login',
                  Main: 'record',
                  Info: 'info',
                  RecordingInProgress: 'recording',
                  AuthCallback: 'auth/callback',
                },
              },
            }}
            fallback={<></>}
            onStateChange={(state) => {
              const route = state?.routes[state.index]?.name
              if (route) {
                logPosthogScreenChange(route)
              }
            }}
          >
            <RootStack.Navigator
              screenOptions={{
                headerShown: false,
                headerTintColor: '#000000',
                headerStyle: {
                  backgroundColor: '#ffffff',
                },
              }}
            >
              <RootStack.Screen name="Login" component={LoginScreen} />
              <RootStack.Screen name="Main" component={RecordingsScreen} />
              <RootStack.Screen name="Info" component={InfoScreen} />
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
          <UpdateModal />
        </AppInitialization>
      </QueryClientProvider>
    </GestureHandlerRootView>
  )
}

export default App
