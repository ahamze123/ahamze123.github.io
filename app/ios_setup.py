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

# ---------- Block Buddies' own plugin: the App Store purchase (the full game) and a second copy of the save ----------
# (app/ios-src: BBStorePlugin.swift, and BBViewController.swift, which registers it; Main.storyboard is pointed at it)
SRC = os.path.join(HERE, 'ios-src')
OWN = [('BBStorePlugin.swift', 'BB57A0E00000000000000001', 'BB57A0E00000000000000002'),
       ('BBViewController.swift', 'BB57A0E00000000000000003', 'BB57A0E00000000000000004')]
for f, _, _ in OWN:
    shutil.copy(os.path.join(SRC, f), os.path.join(APP, f))
s = open(pj).read()
if 'BBStorePlugin.swift' not in s:
    s = s.replace('/* Begin PBXBuildFile section */\n', '/* Begin PBXBuildFile section */\n' + ''.join(
        '\t\t%s /* %s in Sources */ = {isa = PBXBuildFile; fileRef = %s /* %s */; };\n' % (b, f, r, f) for f, r, b in OWN), 1)
    s = s.replace('/* Begin PBXFileReference section */\n', '/* Begin PBXFileReference section */\n' + ''.join(
        '\t\t%s /* %s */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = %s; sourceTree = "<group>"; };\n' % (r, f, f) for f, r, b in OWN), 1)
    m = re.search(r'\n(\t+)[0-9A-F]{24} /\* AppDelegate\.swift \*/,\n', s)
    assert m, 'the App group in project.pbxproj'
    s = s[:m.end()] + ''.join('%s%s /* %s */,\n' % (m.group(1), r, f) for f, r, b in OWN) + s[m.end():]
    m = re.search(r'\n(\t+)[0-9A-F]{24} /\* AppDelegate\.swift in Sources \*/,\n', s)
    assert m, 'the Sources phase in project.pbxproj'
    s = s[:m.end()] + ''.join('%s%s /* %s in Sources */,\n' % (m.group(1), b, f) for f, r, b in OWN) + s[m.end():]
    open(pj, 'w').write(s)
sb = os.path.join(APP, 'Base.lproj', 'Main.storyboard')
t = open(sb).read()
t = t.replace('customClass="CAPBridgeViewController" customModule="Capacitor"', 'customClass="BBViewController" customModule="App" customModuleProvider="target"')
assert 'customClass="BBViewController"' in t, 'Main.storyboard'
open(sb, 'w').write(t)
print('BBStore plugin added')
