#!/usr/bin/env python3
"""Make the iPad app's web files (app/www) from the website: the same game (index.html), the hero cards, the 3D heroes,
the music and the icons. Run from anywhere: python3 app/make_www.py [--test]

What changes in the app:
  - window.BB_APP is set first thing, so the game knows it is the App Store app (no "Add to Home Screen" tips; each tablet
    gets its own family code for online play)
  - the fonts come with the app (from the @fontsource packages that `npm install` puts in app/node_modules) instead of
    from Google, so nothing loads from other websites and the letters look right without the internet
  - --test adds a small helper for the simulator check in the GitHub workflow: it writes BBTEST lines to the console and
    taps Play by itself. The App Store build never has it.
"""
import os, re, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WWW = os.path.join(HERE, 'www')
TEST = '--test' in sys.argv

APP_HEAD = ("<script>window.BB_APP=1;"
            "try{if(navigator.standalone!==true)Object.defineProperty(navigator,'standalone',{get:function(){return true;}});}catch(e){}"
            "</script>")

TEST_HOOK = r"""<script>(function(){var log=function(){try{console.log('BBTEST '+[].slice.call(arguments).join(' '));}catch(e){}};
window.addEventListener('error',function(e){log('ERROR',e.message,(e.filename||'').split('/').pop()+':'+e.lineno);});
var n=0,t0=Date.now();var iv=setInterval(function(){n++;try{if(typeof G==='undefined'){if(n%10===0)log('waiting for the game',n);return;}
 if(G.mode==='title'&&!window.__tT){window.__tT=1;var c=document.createElement('canvas');log('title',Math.round((Date.now()-t0)/1000)+'s',JSON.stringify({w:innerWidth,h:innerHeight,dpr:devicePixelRatio,webgl2:!!c.getContext('webgl2'),standalone:navigator.standalone,app:!!window.BB_APP}));
   setTimeout(function(){var b=document.getElementById('bplay');log('tap Play',!!b);if(b)b.click();setTimeout(function(){try{if(typeof closeIntro==='function'&&document.getElementById('introbox')&&!document.getElementById('introbox').hidden)closeIntro();var g=0;while(typeof DLG!=='undefined'&&DLG&&g++<60){DLG.shown=1e9;advanceDialog();}[].forEach.call(document.querySelectorAll('.modal'),function(m){m.hidden=true;});if(G.mode==='menu')G.mode='play';log('into the game',G.mode);}catch(e){log('skip intro',e.message);}},8000);},25000);}
 if(G.mode==='play'&&!window.__tP){window.__tP=1;log('playing',Math.round((Date.now()-t0)/1000)+'s');
   setTimeout(function(){try{if(typeof closeIntro==='function'&&document.getElementById('introbox')&&!document.getElementById('introbox').hidden)closeIntro();var g=0;while(typeof DLG!=='undefined'&&DLG&&g++<60){DLG.shown=1e9;advanceDialog();}}catch(e){log('intro',e.message);}},4000);}
 if(n%15===0)log('tick',G.mode,'frame',(typeof ERRS!=='undefined'?ERRS.frame:0),'errors',(typeof ERRS!=='undefined'?ERRS.n:0),'music',(typeof TRK!=='undefined'?TRK.st+(TRK.failed?'-failed':'')+' '+(TRK.cur||''):'-'),'fonts',document.fonts?document.fonts.status:'-',
   (function(){try{return [].slice.call(document.fonts).filter(function(f){return f.status==='loaded';}).map(function(f){return f.family;}).filter(function(v,i,a){return a.indexOf(v)===i;}).join('/');}catch(e){return '';}})());
}catch(e){log('hook error',e.message);}},1000);})();</script>"""

# the fonts the game uses, from the @fontsource packages (the same fonts as the website gets from Google Fonts)
FONTS = [('lilita-one', ['400.css']), ('nunito', ['700.css', '800.css', '900.css']),
         ('baloo-bhaijaan-2', ['500.css', '600.css', '700.css', '800.css'])]


def local_fonts():
    nm = os.path.join(HERE, 'node_modules', '@fontsource')
    links = []
    for pkg, css in FONTS:
        src = os.path.join(nm, pkg)
        if not os.path.isdir(src):
            print('font package missing (run npm install in app/):', pkg)
            return None
        dst = os.path.join(WWW, 'fonts', pkg)
        os.makedirs(dst, exist_ok=True)
        shutil.copytree(os.path.join(src, 'files'), os.path.join(dst, 'files'), dirs_exist_ok=True)
        for c in css:
            p = os.path.join(src, c)
            if not os.path.exists(p):
                print('font file missing:', pkg, c)
                continue
            shutil.copy(p, dst)
            links.append('<link rel="stylesheet" href="fonts/%s/%s">' % (pkg, c))
    return ''.join(links)


def main():
    if os.path.exists(WWW):
        shutil.rmtree(WWW)
    os.makedirs(WWW)
    html = open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read()
    assert '<head>' in html and 'BB_STANDALONE' in html, 'index.html is not the website build'
    # first thing in <head>: the app flag (before any of the game's scripts)
    html = html.replace('<head>', '<head>' + APP_HEAD, 1)
    # the website's install bits are not needed in an app
    html = re.sub(r'<link rel="manifest"[^>]*>', '', html)
    # fonts: bundled with the app instead of Google Fonts
    fl = local_fonts()
    if fl:
        n0 = len(html)
        html = re.sub(r'<link rel="preconnect" href="https://fonts\.(googleapis|gstatic)\.com"[^>]*>', '', html)
        html, k = re.subn(r'<link rel="stylesheet" href="https://fonts\.googleapis\.com/[^"]*">', '', html)
        html = html.replace('</head>', fl + '</head>', 1)
        print('fonts bundled (%d Google font links replaced)' % k)
    if TEST:
        html = html.replace('</head>', TEST_HOOK + '</head>', 1)
        print('simulator test helper added')
    open(os.path.join(WWW, 'index.html'), 'w', encoding='utf-8').write(html)
    # the hero cards, the music and the icons (v27.7: no 3D heroes any more, so the .glb files stay out of the app)
    for d in ('cards', 'music'):
        if os.path.isdir(os.path.join(ROOT, d)):
            shutil.copytree(os.path.join(ROOT, d), os.path.join(WWW, d))
    for f in ('icon-192.png', 'icon-512.png', 'apple-touch-icon.png'):
        if os.path.exists(os.path.join(ROOT, f)):
            shutil.copy(os.path.join(ROOT, f), WWW)
    size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(WWW) for f in fs)
    print('app/www ready: %.1f MB' % (size / 1e6))


if __name__ == '__main__':
    main()
