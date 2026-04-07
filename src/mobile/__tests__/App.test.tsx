/**
 * @format
 */

import React from 'react';
import ReactTestRenderer from 'react-test-renderer';
import App from '../App';

jest.mock('@react-navigation/native', () => ({
  NavigationContainer: ({ children }: { children: React.ReactNode }) => children,
  useFocusEffect: () => undefined,
}));

jest.mock('@react-navigation/bottom-tabs', () => ({
  createBottomTabNavigator: () => {
    const ReactLocal = require('react');

    return {
      Navigator: ({ children }: { children: React.ReactNode }) => ReactLocal.createElement(ReactLocal.Fragment, null, children),
      Screen: ({ component: Component }: { component: React.ComponentType }) => ReactLocal.createElement(Component),
    };
  },
}));

jest.mock('react-native-nitro-sound', () => ({
  startRecorder: jest.fn(),
  stopRecorder: jest.fn(),
  pauseRecorder: jest.fn(),
  resumeRecorder: jest.fn(),
  addRecordBackListener: jest.fn(),
  removeRecordBackListener: jest.fn(),
  startPlayer: jest.fn(),
  stopPlayer: jest.fn(),
  addPlayBackListener: jest.fn(),
  removePlayBackListener: jest.fn(),
  addPlaybackEndListener: jest.fn(),
  removePlaybackEndListener: jest.fn(),
  mmssss: (value: number) => String(value),
}));

jest.mock('react-native-mmkv', () => ({
  createMMKV: () => ({
    getString: jest.fn(),
    set: jest.fn(),
  }),
}));

jest.mock('../src/services/authService', () => ({
  login: jest.fn(),
}));

test('renders correctly', async () => {
  await ReactTestRenderer.act(() => {
    ReactTestRenderer.create(<App />);
  });
});
