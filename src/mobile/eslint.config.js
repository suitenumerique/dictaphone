import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import reactHooks from 'eslint-plugin-react-hooks'
import tanstackQuery from '@tanstack/eslint-plugin-query'
import reactRefresh from 'eslint-plugin-react-refresh'
import prettier from 'eslint-config-prettier'

export default [
  {
    ignores: [
      'dist',
      '.eslintrc.cjs',
      '.prettierrc.js',
      'babel.config.js',
      'jest.config.js',
      'metro.config.js',
      'react-native.config.js',
    ],
  },

  js.configs.recommended,
  ...tseslint.configs.recommended,

  {
    files: ['**/*.{ts,tsx,js,jsx}'],

    languageOptions: {
      parser: tseslint.parser,
      ecmaVersion: 2020,
      sourceType: 'module',
    },

    plugins: {
      'react-hooks': reactHooks,
      '@tanstack/query': tanstackQuery,
      'react-refresh': reactRefresh,
    },

    rules: {
      ...reactHooks.configs.recommended.rules,
      ...tanstackQuery.configs.recommended.rules,

      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],
    },
  },

  prettier,
]
