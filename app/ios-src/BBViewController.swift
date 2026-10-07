import UIKit
import Capacitor

// The app's screen: Capacitor's, plus Block Buddies' own plugin (BBStore: the App Store purchase and the save copy).
// ios_setup.py points Main.storyboard at this class.
class BBViewController: CAPBridgeViewController {
    override open func capacitorDidLoad() {
        bridge?.registerPluginInstance(BBStorePlugin())
    }
}
