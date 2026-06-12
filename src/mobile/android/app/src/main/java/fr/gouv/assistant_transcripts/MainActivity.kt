package fr.gouv.assistant_transcripts
import expo.modules.ReactActivityDelegateWrapper

import android.os.Bundle
import com.swmansion.rnscreens.fragment.restoration.RNScreensFragmentFactory
import com.facebook.react.ReactActivity
import com.facebook.react.ReactActivityDelegate
import com.facebook.react.defaults.DefaultNewArchitectureEntryPoint.fabricEnabled
import com.facebook.react.defaults.DefaultReactActivityDelegate
import com.zoontek.rnbootsplash.RNBootSplash
import android.content.Intent
import android.util.Log
import android.net.Uri

class MainActivity : ReactActivity() {

    /**
     * Returns the name of the main component registered from JavaScript. This is used to schedule
     * rendering of the component.
     */
    override fun getMainComponentName(): String = "Assistant Transcripts"

    /**
     * Returns the instance of the [ReactActivityDelegate]. We use [DefaultReactActivityDelegate]
     * which allows you to enable New Architecture with a single boolean flags [fabricEnabled]
     */
    override fun createReactActivityDelegate(): ReactActivityDelegate =
        ReactActivityDelegateWrapper(this, BuildConfig.IS_NEW_ARCHITECTURE_ENABLED, DefaultReactActivityDelegate(this, mainComponentName, fabricEnabled))

    override fun onCreate(savedInstanceState: Bundle?) {
//        val data: Uri? = intent?.data
//        Log.d("DEEPLINK", "onCreate URI = $data")
//        Log.d("DEEPLINK", "onCreate Intent = $intent")

        supportFragmentManager.fragmentFactory = RNScreensFragmentFactory()
        RNBootSplash.init(this, R.style.BootTheme) // ⬅️ initialize the splash screen
        super.onCreate(savedInstanceState)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)

//        val data: Uri? = intent.data
//        Log.d("DEEPLINK", "onNewIntent URI = $data")
//        Log.d("DEEPLINK", "onNewIntent Intent = $intent")
    }

}
