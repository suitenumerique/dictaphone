import '@gouvfr-lasuite/ui-kit/style'
import '@gouvfr-lasuite/ui-kit/fonts/Marianne'
import './styles/globals.scss'

import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import { CunninghamProvider } from '@gouvfr-lasuite/ui-kit'
import { useTranslation } from 'react-i18next'

// eslint-disable-next-line react-refresh/only-export-components
function RootApp() {
  const { i18n } = useTranslation()
  return (
    <React.StrictMode>
      <CunninghamProvider theme="dsfr-light" currentLocale={i18n.language}>
        <App />
      </CunninghamProvider>
    </React.StrictMode>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(<RootApp />)
