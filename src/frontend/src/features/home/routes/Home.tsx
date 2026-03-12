import { useTranslation } from 'react-i18next'
import { authUrl, useUser } from '@/features/auth'
import {
  Hero,
  MainLayout,
  ProConnectButton,
  Spinner,
} from '@gouvfr-lasuite/ui-kit'
import LogoApp from '@/layout/LogoApp'
import { HeaderRight } from '@/layout/HeaderRight'
import { useConfig } from '@/api/useConfig'
import { Button } from '@gouvfr-lasuite/cunningham-react'
import { ListFilesParams, useListMyFiles } from '@/features/files/api/listFiles'
import { useCreateFile } from '@/features/files/api/createFile'
import { FileTrigger, Pressable } from 'react-aria-components'

const listFilesQueryParams: ListFilesParams = {
  filters: {
    type: 'audio_recording',
    upload_state: 'ready',
    is_creator_me: true,
    is_deleted: false,
  },
  pagination: {
    page: 1,
    pageSize: 20,
  },
}

export const Home = () => {
  const { t } = useTranslation('home')
  const { isLoggedIn, isLoading } = useUser()

  const { data: appConfig } = useConfig()
  const filesQ = useListMyFiles(listFilesQueryParams)
  const createFileMutation = useCreateFile()

  const handleNewFilePicked = (file: File) => {
    createFileMutation.mutate({
      file,
      onProgress: (progress) => {
        console.log(`Upload progress: ${progress}%`)
      },
    })
  }

  if (isLoading) return <Spinner />

  if (!isLoggedIn) {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh',
        }}
      >
        <Hero
          banner="/assets/hero-beta.png"
          title={t('title')}
          subtitle={t('subtitle')}
          logo={<LogoApp size={100} />}
          mainButton={
            appConfig?.use_proconnect_button ? (
              <ProConnectButton
                onClick={() => window.location.replace(authUrl())}
              />
            ) : (
              <Button onClick={() => window.location.replace(authUrl())}>
                {t('login')}
              </Button>
            )
          }
        />
      </div>
    )
  }

  return (
    <MainLayout
      icon={<LogoApp />}
      hideLeftPanelOnDesktop={true}
      rightHeaderContent={<HeaderRight />}
    >
      <FileTrigger
        acceptedFileTypes={appConfig?.audio_recording?.allowed_mimetypes ?? []}
        onSelect={(e) => {
          if (e && e.item(0)) {
            const file = e.item(0) as File
            handleNewFilePicked(file)
          }
        }}
      >
        <Pressable>
          <Button
            aria-label={'Load audio recording from your device'}
            disabled={createFileMutation.isPending}
            data-attr="input-file-select-audio-recording"
          >
            Add recording
          </Button>
        </Pressable>
      </FileTrigger>

      {filesQ.isPending && <span>Loading...</span>}
      {filesQ.data && filesQ.data.count === 0 && <span>No files</span>}
      {filesQ.data && filesQ.data.results.length > 0 && (
        <div>
          {filesQ.data.results.map((file) => (
            <div key={file.id}>
              <span>{file.title}</span>
              {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
              <audio controls src={file.url!} />
            </div>
          ))}
        </div>
      )}
    </MainLayout>
  )
}
