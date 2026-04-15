import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Platform, StatusBar } from 'react-native';
import { useMemo } from 'react';

export function useInsets(params?: {
  paddingTop?: number;
  paddingBottom?: number;
  paddingLeft?: number;
  paddingRight?: number;
}) {
  const insets = useSafeAreaInsets();

  return useMemo(
    () => ({
      paddingTop:
        insets.top +
        (params?.paddingTop ?? 0) +
        (Platform.OS === 'android' ? StatusBar.currentHeight ?? 0 : 0),
      paddingBottom: insets.bottom + (params?.paddingBottom ?? 0),
      paddingLeft: insets.left + (params?.paddingLeft ?? 8),
      paddingRight: insets.right + (params?.paddingRight ?? 8),
      flex: 1,
      backgroundColor: 'white',
    }),
    [
      insets.bottom,
      insets.left,
      insets.right,
      insets.top,
      params?.paddingBottom,
      params?.paddingLeft,
      params?.paddingRight,
      params?.paddingTop,
    ],
  );
}
