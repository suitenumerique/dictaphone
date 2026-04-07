const { getDefaultConfig } = require('@react-native/metro-config');

/**
 * Metro configuration
 * https://reactnative.dev/docs/metro
 *
 * @type {import('@react-native/metro-config').MetroConfig}
 */
const config = {};

module.exports = (() => {
  const config = getDefaultConfig(__dirname);

  config.transformer.babelTransformerPath = require.resolve(
    'react-native-svg-transformer',
  );

  config.resolver.assetExts = config.resolver.assetExts.filter(
    ext => ext !== 'svg',
  );
  config.resolver.sourceExts.push('svg');

  return config;
})();
