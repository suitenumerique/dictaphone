This is a [**React Native**](https://reactnative.dev) project, bootstrapped using [`@react-native-community/cli`](https://github.com/react-native-community/cli).

# Getting Started

> **Note**: Make sure you have completed the [Set Up Your Environment](https://reactnative.dev/docs/set-up-your-environment) guide before proceeding.

First of all install mobile deps.

```sh
yarn install
```

## Step 1: Start Metro

First, you will need to run **Metro**, the JavaScript build tool for React Native.

To start the Metro dev server, run the following command from the root of your React Native project:

```sh
yarn start
```

## Step 2: Build and run your app

With Metro running, open a new terminal window/pane from the root of your React Native project, and use one of the following commands to build and run your Android or iOS app:

### Android

```sh
yarn android
```

### iOS

_NB: requires a Mac OS computer._

For iOS, remember to install CocoaPods dependencies (this only needs to be run on first clone or after updating native deps).

The first time you create a new project, run the Ruby bundler to install CocoaPods itself:

```sh
bundle install
```

Then, and every time you update your native dependencies, run in `ios` folder:

```sh
bundle exec pod install
```

For more information, please visit [CocoaPods Getting Started guide](https://guides.cocoapods.org/using/getting-started.html).

```sh
yarn ios
```

If you have build issues for ios, clean everything and restart from scratch (in `src/mobile` folder):

```bash
rm -rf node_modules
rm -rf ios/Pods
rm -rf ./vendor/bundle
rm -rf ~/Library/Developer/Xcode/DevrivedData
```

---

If everything is set up correctly, you should see your new app running in the Android Emulator, iOS Simulator, or your connected device.

This is one way to run your app — you can also build it directly from Android Studio or Xcode.

# Other

## Generate assets

```bash
yarn react-native-bootsplash generate src/assets/logo.svg \
  --platforms=android,ios \
  --background=F5FCFF \
  --logo-width=100 \
  --assets-output=assets/bootsplash \
  --flavor=main

npx rn-app-icons --input src/assets/icon.svg
find ios -name "*.png" -exec convert {} -background "#F5FCFF" -flatten -alpha off {} \;
```

## Release

Run `bash scripts/release_bump.sh <version>`, this will update the version and build number in the following places:

- [package.json](./package.json)
- [ios/AssistantTranscripts.xcodeproj/project.pbxproj](./ios/AssistantTranscripts.xcodeproj/project.pbxproj)
- [android/app/build.gradle](./android/app/build.gradle)

### iOS

- Connect XCode to the appropriate Apple Developer account
- Open project in Xcode
- Select "Any iOS device (arm64)" as target
- In the `Product` menu, select `Archive`
- In the `Distribute` menu, select `App Store Connect`
- From there everything happens on https://appstoreconnect.apple.com/

### Android

- Open project in Android Studio
- (ask for the keystore)
- In the `build` menu, click on `Generate Signed App Bundle or APK`, select `Android App Bundle`, select the appropriate keystore, `release` as build variant, and then `create`.
- From there everything happens on https://play.google.com/console/
