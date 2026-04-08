import { QueryClient } from '@tanstack/react-query'
import NetInfo from '@react-native-community/netinfo';
import { onlineManager } from '@tanstack/react-query';

export const queryClient = new QueryClient()


onlineManager.setEventListener(setOnline => {
  return NetInfo.addEventListener(state => {
    setOnline(!!state.isConnected);
  });
});
