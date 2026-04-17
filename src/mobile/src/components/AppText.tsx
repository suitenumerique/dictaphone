import React from 'react';
import { StyleSheet, Text, type TextProps, type TextStyle } from 'react-native';
import { colors } from './colors';

type AppTextVariant =
  | 'heading'
  | 'subtitle'
  | 'body'
  | 'bodyStrong'
  | 'muted'
  | 'button';

type AppTextSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl';

type AppTextProps = TextProps & {
  variant?: AppTextVariant;
  size?: AppTextSize;
  color?: string;
  weight?: TextStyle['fontWeight'];
  align?: 'left' | 'right' | 'center';
};

const typography = StyleSheet.create({
  base: {
    includeFontPadding: false,
    fontFamily: 'Marianne',
  },
  heading: {
    fontSize: 18,
    lineHeight: 24,
    fontWeight: '700',
    color: colors.textPrimary,
  },
  subtitle: {
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '500',
    color: colors.neutralSecondary,
  },
  body: {
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '400',
    color: colors.textSecondary,
  },
  bodyStrong: {
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '700',
    color: colors.textPrimary,
  },
  muted: {
    fontSize: 12,
    lineHeight: 18,
    fontWeight: '400',
    color: colors.neutralSecondary,
  },
  button: {
    fontSize: 18,
    color: colors.backgroundBase,
  },
  xs: {
    fontSize: 11,
    lineHeight: 14,
  },
  sm: {
    fontSize: 12,
    lineHeight: 16,
  },
  md: {
    fontSize: 14,
    lineHeight: 20,
  },
  lg: {
    fontSize: 16,
    lineHeight: 22,
  },
  xl: {
    fontSize: 20,
    lineHeight: 26,
  },

  left: {
    textAlign: 'left',
  },
  center: {
    textAlign: 'center',
  },
  right: {
    textAlign: 'right',
  },
});

const variantStyles: Record<AppTextVariant, TextStyle> = {
  heading: typography.heading,
  subtitle: typography.subtitle,
  body: typography.body,
  bodyStrong: typography.bodyStrong,
  muted: typography.muted,
  button: typography.button,
};

const sizeStyles: Record<AppTextSize, TextStyle> = {
  xs: typography.xs,
  sm: typography.sm,
  md: typography.md,
  lg: typography.lg,
  xl: typography.xl,
};

const alignStyles: Record<NonNullable<AppTextProps['align']>, TextStyle> = {
  left: typography.left,
  center: typography.center,
  right: typography.right,
};

export function AppText({
  variant = 'body',
  size,
  color,
  weight,
  align,
  style,
  children,
  ...props
}: AppTextProps) {
  return (
    <Text
      {...props}
      style={[
        typography.base,
        variantStyles[variant],
        size ? sizeStyles[size] : null,
        align ? alignStyles[align] : null,
        color ? { color } : null,
        weight ? { fontWeight: weight } : null,
        style,
      ]}
    >
      {children}
    </Text>
  );
}
