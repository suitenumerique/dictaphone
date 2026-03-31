import '@gouvfr-lasuite/ui-kit/style'
import '@gouvfr-lasuite/ui-kit/fonts/Marianne'
import './styles/globals.scss'

import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import { CunninghamProvider } from '@gouvfr-lasuite/ui-kit'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <CunninghamProvider theme="dsfr-light">
      <App />
    </CunninghamProvider>
  </React.StrictMode>
)
