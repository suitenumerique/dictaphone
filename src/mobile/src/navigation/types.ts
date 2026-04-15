export type RootStackParamList = {
  Login: undefined;
  Main: undefined;
  RecordingInProgress: undefined;
  RecordingDetails: { id: string };
  AuthCallback: {
    sessionId?: string;
    csrfToken?: string;
  };
};
