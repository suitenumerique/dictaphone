export type RootStackParamList = {
  Login: undefined
  Main: undefined
  RecordingInProgress: undefined
  RecordingDetails: { id: string }
  AuthCallback:
    | {
        code?: string
        state?: string
      }
    | undefined
}
