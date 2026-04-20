import React from 'react'
import { StyleSheet, Text, type TextProps, type TextStyle } from 'react-native'
import { colors } from './colors'

type AppTextVariant =
  | 'heading'
  | 'subtitle'
  | 'body'
  | 'bodyMedium'
  | 'bodyBold'
  | 'muted'
  | 'button'

type AppTextSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl'

type AppTextProps = TextProps & {
  variant?: AppTextVariant
  size?: AppTextSize
  color?: string
  weight?: TextStyle['fontWeight']
  align?: 'left' | 'right' | 'center'
}

const typography = StyleSheet.create({
  base: {
    includeFontPadding: false,
    fontFamily: 'Marianne-Regular',
  },
  heading: {
    fontSize: 18,
    lineHeight: 24,
    fontFamily: 'Marianne-Bold',
    color: colors.textPrimary,
  },
  subtitle: {
    fontSize: 14,
    lineHeight: 20,
    color: colors.neutralSecondary,
  },
  body: {
    fontSize: 15,
    lineHeight: 20,
    fontFamily: 'Marianne-Regular',
    color: colors.textSecondary,
  },
  bodyMedium: {
    fontSize: 15,
    lineHeight: 20,
    fontFamily: 'Marianne-Medium',
    color: colors.textPrimary,
  },
  bodyBold: {
    fontSize: 15,
    lineHeight: 20,
    fontFamily: 'Marianne-Bold',
    color: colors.textPrimary,
  },
  muted: {
    fontSize: 12,
    lineHeight: 18,
    color: colors.neutralSecondary,
  },
  button: {
    marginTop: -3,
    fontSize: 18,
    fontFamily: 'Marianne-Medium',
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
    fontSize: 15,
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
})

const variantStyles: Record<AppTextVariant, TextStyle> = {
  heading: typography.heading,
  subtitle: typography.subtitle,
  body: typography.body,
  bodyMedium: typography.bodyMedium,
  bodyBold: typography.bodyBold,
  muted: typography.muted,
  button: typography.button,
}

const sizeStyles: Record<AppTextSize, TextStyle> = {
  xs: typography.xs,
  sm: typography.sm,
  md: typography.md,
  lg: typography.lg,
  xl: typography.xl,
}

const alignStyles: Record<NonNullable<AppTextProps['align']>, TextStyle> = {
  left: typography.left,
  center: typography.center,
  right: typography.right,
}

export function AppText({
  variant = 'body',
  size,
  color,
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
        style,
      ]}
    >
      {children}
    </Text>
  )
}
