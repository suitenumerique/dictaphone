module.exports = {
  presets: ['module:@react-native/babel-preset'],
  plugins: [
    [
      'module-resolver',
      {
        root: ['./src'],
        alias: {
          '@': './src',
          crypto: 'react-native-quick-crypto',
          stream: 'readable-stream',
          buffer: 'react-native-quick-crypto',
        },
      },
    ],
    // must be the last one
    'react-native-worklets/plugin',
  ],
}
