#!/usr/bin/env python3
"""Set up the Xcode project that `npx cap add ios` made (app/ios/App): an iPad game that fills the screen.
Runs on the Mac in the GitHub workflow, after `npx cap add ios`.
  - Info.plist: the name under the icon, no status bar, all four ways round on an iPad, no special encryption
    (so App Store Connect does not ask about export rules for every build)
  - iPad only (the game is made for tablets)
  - the app icon (app/resources/icon-1024.png) and the launch screen (app/resources/splash-2732.png)
  - the Apple team, when APPLE_TEAM_ID is set (for the App Store build)
"""
import glob, json, os, plistlib, re, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
IOS = os.path.join(HERE, 'ios', 'App')
APP = os.path.join(IOS, 'App')

# ---------- Info.plist ----------
p = os.path.join(APP, 'Info.plist')
with open(p, 'rb') as f:
    pl = plistlib.load(f)
pl['CFBundleDisplayName'] = 'Block Buddies'
pl['UIStatusBarHidden'] = True
pl['UIViewControllerBasedStatusBarAppearance'] = False
pl['ITSAppUsesNonExemptEncryption'] = False
pl['LSApplicationCategoryType'] = 'public.app-category.family-games'
ors = ['UIInterfaceOrientationLandscapeLeft', 'UIInterfaceOrientationLandscapeRight', 'UIInterfaceOrientationPortrait', 'UIInterfaceOrientationPortraitUpsideDown']
pl['UISupportedInterfaceOrientations'] = ors
pl['UISupportedInterfaceOrientations~ipad'] = ors
with open(p, 'wb') as f:
    plistlib.dump(pl, f)
print('Info.plist ready')

# ---------- the Xcode project: iPad only, and the Apple team ----------
pj = os.path.join(IOS, 'App.xcodeproj', 'project.pbxproj')
s = open(pj).read()
s, n = re.subn(r'TARGETED_DEVICE_FAMILY = "?[0-9,]+"?;', 'TARGETED_DEVICE_FAMILY = 2;', s)
print('iPad only:', n, 'build settings')
team = os.environ.get('APPLE_TEAM_ID', '').strip()
if team:
    if 'DEVELOPMENT_TEAM' in s:
        s = re.sub(r'DEVELOPMENT_TEAM = [^;]*;', 'DEVELOPMENT_TEAM = %s;' % team, s)
    else:
        s = s.replace('PRODUCT_BUNDLE_IDENTIFIER = ', 'DEVELOPMENT_TEAM = %s;\n\t\t\t\tPRODUCT_BUNDLE_IDENTIFIER = ' % team)
    s = re.sub(r'CODE_SIGN_STYLE = [^;]*;', 'CODE_SIGN_STYLE = Automatic;', s)
    print('team set')
open(pj, 'w').write(s)

# ---------- the app icon and the launch screen ----------
ic = os.path.join(APP, 'Assets.xcassets', 'AppIcon.appiconset')
for f in glob.glob(os.path.join(ic, '*.png')):
    os.remove(f)
shutil.copy(os.path.join(HERE, 'resources', 'icon-1024.png'), os.path.join(ic, 'AppIcon-1024.png'))
json.dump({'images': [{'filename': 'AppIcon-1024.png', 'idiom': 'universal', 'platform': 'ios', 'size': '1024x1024'}],
           'info': {'author': 'xcode', 'version': 1}}, open(os.path.join(ic, 'Contents.json'), 'w'), indent=2)
sp = os.path.join(APP, 'Assets.xcassets', 'Splash.imageset')
if os.path.isdir(sp):
    for f in glob.glob(os.path.join(sp, '*.png')):
        shutil.copy(os.path.join(HERE, 'resources', 'splash-2732.png'), f)
print('icon and launch screen ready')
