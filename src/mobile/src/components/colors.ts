export const colors = {
  primary: '#3E5DE7',
  primaryPressed: '#2845c1',
  secondary: '#dae2ff',
  secondaryPressed: '#c8d3ff',

  backgroundError: '#cf202d',
  backgroundErrorPressed: '#9d2227',
  backgroundErrorSecondary: '#ffdad7',
  backgroundErrorSecondaryPressed: '#ffc7c2',
  errorSecondary: '#bd0f23',

  warning: '#984800',
  warningSurface: '#FFEEDF',
  warningBorder: '#FFCA9C',

  textPrimary: '#111827',
  textSecondary: '#2B3448',

  backgroundBase: '#FFFFFF',
  backgroundSubtle: '#F8FAFC',
  backgroundSubtlePressed: '#F2F4F7',

  neutralSecondary: '#555E74',
  backgroundNeutralSecondary: '#DFE2EA',
  backgroundNeutralSecondaryPressed: '#cfd5de',
  neutralTertiary: '#626A80',
  backgroundNeutralTertiary: '#EEF1F4',

  shadowDefault: '#D9DCE3',

  surfacePrimary: '#DFE2EA',

  overlayBackdrop: 'rgba(15, 23, 42, 0.45)',
} as const satisfies Record<string, string>;
