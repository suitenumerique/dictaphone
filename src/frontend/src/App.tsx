import { Suspense } from 'react'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { QueryClientProvider } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useLang } from 'hoofd'
import { Route, Switch } from 'wouter'
import { I18nProvider } from 'react-aria-components'
import { Layout } from './layout/Layout'
import { NotFoundScreen } from './components/NotFoundScreen'
import './i18n/init'
import { queryClient } from '@/api/queryClient'
import { AppInitialization } from '@/components/AppInitialization'
import { HomePage } from '@/pages/HomePage.tsx'
import { RecordingPage } from '@/pages/RecordingPage.tsx'
import { RecordingsPage } from '@/pages/RecordingsPage.tsx'
import { Toaster } from '@/features/ui/components/toaster/Toaster.tsx'
import { RecordPage } from '@/pages/RecordPage.tsx'

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
                key={'recordings'}
                path={'/recordings'}
                component={RecordingsPage}
              />
              <Route
                key={'new-recording'}
                path={'/new-recording'}
                component={RecordPage}
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
            buttonPosition="bottom-left"
          />
        </I18nProvider>
      </Suspense>
    </QueryClientProvider>
  )
}

export default App
