#!/usr/bin/env python3
"""App Store Connect checks before an upload (runs in the GitHub workflow with the Apple API key):
  python3 asc.py prepare BUNDLE_ID NAME
    - registers the bundle ID (the app's ID at Apple) if it is not there yet
    - checks that the app exists in App Store Connect (that one only the account owner can make, on the website)
Prints one line: READY, or NO_APP (the app has to be made in App Store Connect first), or an error.
Needs ASC_KEY_ID, ASC_ISSUER_ID and the key file ~/private_keys/AuthKey_<ASC_KEY_ID>.p8, and the packages pyjwt and cryptography.
"""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request
import jwt  # pyjwt

API = 'https://api.appstoreconnect.apple.com'


def token():
    kid, iss = os.environ['ASC_KEY_ID'].strip(), os.environ['ASC_ISSUER_ID'].strip()
    key = open(os.path.expanduser('~/private_keys/AuthKey_%s.p8' % kid)).read()
    now = int(time.time())
    return jwt.encode({'iss': iss, 'iat': now, 'exp': now + 900, 'aud': 'appstoreconnect-v1'}, key, algorithm='ES256',
                      headers={'kid': kid, 'typ': 'JWT'})


def call(method, path, body=None):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={'Authorization': 'Bearer ' + token(), 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or 'null')
    except urllib.error.HTTPError as e:
        raise RuntimeError('%s %s: HTTP %s %s' % (method, path, e.code, e.read().decode(errors='replace')[:800]))


def prepare(bundle, name):
    q = urllib.parse.quote(bundle)
    have = call('GET', '/v1/bundleIds?filter[identifier]=%s&limit=5' % q).get('data') or []
    have = [b for b in have if b['attributes'].get('identifier') == bundle]
    if not have:
        call('POST', '/v1/bundleIds', {'data': {'type': 'bundleIds', 'attributes': {'identifier': bundle, 'name': name, 'platform': 'IOS'}}})
        print('registered the bundle ID', bundle, file=sys.stderr)
    else:
        print('bundle ID is registered', file=sys.stderr)
    apps = call('GET', '/v1/apps?filter[bundleId]=%s&limit=5' % q).get('data') or []
    apps = [a for a in apps if a['attributes'].get('bundleId') == bundle]
    if not apps:
        print('NO_APP')
        return
    a = apps[0]['attributes']
    print('READY', json.dumps({'name': a.get('name'), 'sku': a.get('sku'), 'id': apps[0]['id']}))


if __name__ == '__main__':
    if len(sys.argv) >= 4 and sys.argv[1] == 'prepare':
        try:
            prepare(sys.argv[2], sys.argv[3])
        except Exception as e:
            print('ERROR', str(e)[:900])
    else:
        print(__doc__)
