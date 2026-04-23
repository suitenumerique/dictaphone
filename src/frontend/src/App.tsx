import './i18n/init'
import React, { Suspense } from 'react'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { QueryClientProvider } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useLang } from 'hoofd'
import { Route, Switch } from 'wouter'
import { I18nProvider } from 'react-aria-components'
import { Layout } from './layout/Layout'
import { NotFoundScreen } from './components/NotFoundScreen'
import { queryClient } from '@/api/queryClient'
import { AppInitialization } from '@/components/AppInitialization'

import { Toaster } from '@/features/ui/components/toaster/Toaster.tsx'

const HomePage = React.lazy(() => import('@/pages/HomePage.tsx'))
const DownloadMobileAppPage = React.lazy(
  () => import('@/pages/DownloadMobileAppPage.tsx')
)
const RecordingPage = React.lazy(() => import('@/pages/RecordingPage.tsx'))
const RecordingsPage = React.lazy(() => import('@/pages/RecordingsPage.tsx'))
const RecordPage = React.lazy(() => import('@/pages/RecordPage.tsx'))
const LegalTermsPage = React.lazy(() => import('@/pages/legal/LegalTermsPage'))
const TermsOfServicePage = React.lazy(
  () => import('@/pages/legal/TermsOfServicePage')
)
const AccessibilityPage = React.lazy(
  () => import('@/pages/legal/AccessibilityPage')
)
const PersonalDataPage = React.lazy(
  () => import('@/pages/legal/PersonalDataPage')
)

function App() {
  const { i18n } = useTranslation()
  useLang(i18n.language)

  return (
    <QueryClientProvider client={queryClient}>
      <AppInitialization />
      <Suspense fallback={null}>
        <I18nProvider locale={i18n.language}>
          <Layout>
            <Switch>
              <Route key={'home'} path={'/'} component={HomePage} />
              <Route
                key={'fr-cgu'}
                path={'/modalites-utilisation'}
                component={TermsOfServicePage}
              />
              <Route
                key={'en-cgu'}
                path={'/terms-of-service'}
                component={TermsOfServicePage}
              />
              <Route
                key={'fr-legal-terms'}
                path={'/mentions-legales'}
                component={LegalTermsPage}
              />
              <Route
                key={'en-legal-terms'}
                path={'/legal-terms'}
                component={LegalTermsPage}
              />
              <Route
                key={'fr-accessibilite'}
                path={'/accessibilite'}
                component={AccessibilityPage}
              />
              <Route
                key={'en-accessibility'}
                path={'/accessibility'}
                component={AccessibilityPage}
              />

              <Route
                key={'fr-personal-data'}
                path={'/donnees-personnelles'}
                component={PersonalDataPage}
              />
              <Route
                key={'en-personal-data'}
                path={'/personal-data'}
                component={PersonalDataPage}
              />
              <Route
                key={'recordings'}
                path={'/recordings'}
                component={RecordingsPage}
              />
              <Route
                key={'new-recording'}
                path={'/new-recording'}
                component={RecordPage}
              />
              <Route
                key={'download-mobile-app'}
                path={'/download-mobile-app'}
                component={DownloadMobileAppPage}
              />
              {/*<Route*/}
              {/*  key={'trash'}*/}
              {/*  path={'/trash'}*/}
              {/*  component={DeletedRecordingsPage}*/}
              {/*/>*/}
              <Route key={'recording'} path={'/recordings/:recordingId'}>
                {(params) => <RecordingPage recordingId={params.recordingId} />}
              </Route>
              <Route component={NotFoundScreen} />
            </Switch>
            <Toaster />
          </Layout>
          <ReactQueryDevtools
            initialIsOpen={false}
            buttonPosition="bottom-right"
          />
        </I18nProvider>
      </Suspense>
    </QueryClientProvider>
  )
}

export default App
