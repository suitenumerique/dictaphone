// src/navigation/types.ts
export type RecordingDetailsParams = {
  id: string;
  title: string;
  createdAt: string;
  durationSeconds: number;
  kind: 'local' | 'remote';
};

export type RootStackParamList = {
  Login: undefined;
  Main: undefined;
  RecordingInProgress: undefined;
  RecordingDetails: { recording: RecordingDetailsParams };
  AuthCallback: {
    sessionId?: string;
    csrfToken?: string;
  };
};
