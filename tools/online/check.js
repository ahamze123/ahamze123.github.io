// Online play, tested on the real internet (GitHub's runners): are the public matchmakers up, and can a tablet find and join a
// game hosted by a tablet on a different network? "Different networks" are made by blocking some services for one browser.
// usage: node check.js BASE_URL OUT_DIR [scenario,...]
const {chromium}=require('playwright');const fs=require('fs');
const BASE=process.argv[2]||'https://ahamze123.github.io/';const OUT=process.argv[3]||'out';const ONLY=process.argv[4]?process.argv[4].split(','):null;
fs.mkdirSync(OUT,{recursive:true});const log=(...a)=>{const s=a.map(x=>typeof x==='string'?x:JSON.stringify(x)).join(' ');console.log(s);fs.appendFileSync(OUT+'/log.txt',s+'\n');};
const HOSTS={pj:['0.peerjs.com'],eclipse:['mqtt.eclipseprojects.io'],emqx:['broker.emqx.io'],hivemq:['broker.hivemq.com'],shiftr:['public.cloud.shiftr.io'],mosq:['test.mosquitto.org'],ntfy:['ntfy.sh']};
const rules=block=>block.flatMap(k=>HOSTS[k]||[k]).map(h=>`MAP ${h} ~NOTFOUND`).join(', ');
// ---- 1. the services themselves (from Node, no browser) ----
async function wsCheck(url,proto,first,ms=9000){return new Promise(res=>{const t0=Date.now();let ws;try{ws=new WebSocket(url,proto);}catch(e){res({ok:false,err:String(e).slice(0,80)});return;}
  ws.binaryType='arraybuffer';const done=r=>{try{ws.close();}catch(e){}res({...r,ms:Date.now()-t0});};const to=setTimeout(()=>done({ok:false,err:'timeout'}),ms);
  ws.onopen=()=>{if(first)ws.send(first);};ws.onmessage=ev=>{clearTimeout(to);const d=typeof ev.data==='string'?ev.data.slice(0,60):'bin '+new Uint8Array(ev.data).slice(0,4).join(',');done({ok:true,got:d});};ws.onerror=()=>{};ws.onclose=ev=>{clearTimeout(to);done({ok:false,err:'closed '+ev.code});};});}
function mqttConnect(id,user,pass){const E=new TextEncoder();const s2=s=>{const b=E.encode(s);return [b.length>>8,b.length&255,...b];};let flags=0x02;const pay=[...s2(id)];if(user){flags|=0x80;pay.push(...s2(user));}if(pass){flags|=0x40;pay.push(...s2(pass));}
  const body=[...s2('MQTT'),4,flags,0,60,...pay];return new Uint8Array([0x10,body.length,...body]);}
async function services(){const r={};
  r.peerjs=await wsCheck('wss://0.peerjs.com/peerjs?key=peerjs&id=bbcheck'+Math.random().toString(36).slice(2,10)+'&token=t'+Date.now()+'&version=1.5.4',undefined,null);
  for(const [k,u,user,pass] of [['eclipse','wss://mqtt.eclipseprojects.io:443/mqtt'],['emqx','wss://broker.emqx.io:8084/mqtt'],['hivemq','wss://broker.hivemq.com:8884/mqtt'],['shiftr','wss://public.cloud.shiftr.io','public','public'],['mosq','wss://test.mosquitto.org:8081/mqtt'],['mosq1','wss://test.mosquitto.org:8081']])
    r[k]=await wsCheck(u,['mqtt'],mqttConnect('bbcheck'+Math.random().toString(36).slice(2,8),user,pass));
  try{const t0=Date.now();const x=await fetch('https://ntfy.sh/bbuddies-check-'+Date.now().toString(36),{method:'POST',body:'hello'});r.ntfyPost={ok:x.ok,status:x.status,ms:Date.now()-t0,limit:x.headers.get('x-ratelimit-remaining')||''};}catch(e){r.ntfyPost={ok:false,err:String(e).slice(0,80)};}
  r.ntfyWs=await wsCheck('wss://ntfy.sh/bbuddies-check/ws',undefined,null);
  return r;}
// ---- 1b. the PeerJS cloud server, step by step: does it close a connection, and when? ----
function pjOne(name,steps,ms=12000){return new Promise(res=>{const id='bbflap'+name+Math.random().toString(36).slice(2,8),tok='t'+Math.random().toString(36).slice(2,10);const t0=Date.now();const ev=[];const L=(...a)=>ev.push([Date.now()-t0,...a]);
  let ws;try{ws=new WebSocket('wss://0.peerjs.com/peerjs?key=peerjs&id='+id+'&token='+tok+'&version=1.5.4');}catch(e){res({err:String(e)});return;}
  const send=o=>{try{ws.send(JSON.stringify(o));L('sent',o.type,o.dst===id?'self':o.dst?'other':'');}catch(e){L('senderr');}};
  ws.onopen=()=>{L('open');if(steps.onopen)steps.onopen(send,id);};ws.onmessage=e=>{let m;try{m=JSON.parse(e.data);}catch(x){m={raw:String(e.data).slice(0,40)};}L('msg',m.type,m.src===id?'self':m.src?'other':'',m.payload&&m.payload.msg?m.payload.msg:'');if(m.type==='OPEN'&&steps.onOPEN)steps.onOPEN(send,id);};
  ws.onclose=e=>{L('close',e.code,String(e.reason||'').slice(0,60));};ws.onerror=()=>L('error');
  if(steps.every)setInterval(()=>{if(ws.readyState===1)steps.every(send,id);},steps.everyMs||5000);
  setTimeout(()=>{try{ws.close();}catch(e){}setTimeout(()=>res(ev.slice(0,30)),300);},ms);});}
async function pjFlap(){const r={};
  r.idle=await pjOne('i',{});
  r.heartbeat=await pjOne('h',{every:s=>s({type:'HEARTBEAT'})});
  r.pingSelf=await pjOne('s',{onOPEN:(s,id)=>s({type:'OFFER',dst:id,payload:{bbping:1}}),every:(s,id)=>{s({type:'HEARTBEAT'});s({type:'OFFER',dst:id,payload:{bbping:2}});}});
  r.pingSelfAtOpen=await pjOne('o',{onopen:(s,id)=>s({type:'OFFER',dst:id,payload:{bbping:1}})});
  r.probeOthers=await pjOne('p',{onOPEN:s=>{for(const d of ['bbuddies-zz-game','bbuddies-zz-game2','bbuddies-zz-game3'])s({type:'OFFER',dst:d,payload:{probe:1,ts:Date.now()}});},every:s=>{s({type:'HEARTBEAT'});for(const d of ['bbuddies-zz-game','bbuddies-zz-game2','bbuddies-zz-game3'])s({type:'OFFER',dst:d,payload:{probe:1,ts:Date.now()}});},everyMs:2500});
  return r;}
// ---- 2. TURN relays (does a browser get a relay candidate from them?) ----
async function turnCheck(b){const p=await b.newPage();await p.goto('https://ahamze123.github.io/support.html',{waitUntil:'domcontentloaded'}).catch(()=>{});const r=await p.evaluate(async()=>{const user=(Math.floor(Date.now()/1000)+86400)+':bbuddies';const E=new TextEncoder();
    const k=await crypto.subtle.importKey('raw',E.encode('openrelayprojectsecret'),{name:'HMAC',hash:'SHA-1'},false,['sign']);const sg=new Uint8Array(await crypto.subtle.sign('HMAC',k,E.encode(user)));let bb='';for(const x of sg)bb+=String.fromCharCode(x);
    const T={peerjs:{urls:['turn:eu-0.turn.peerjs.com:3478','turn:us-0.turn.peerjs.com:3478'],username:'peerjs',credential:'peerjsp'},openrelay:{urls:['turn:staticauth.openrelay.metered.ca:80','turn:staticauth.openrelay.metered.ca:443','turn:staticauth.openrelay.metered.ca:443?transport=tcp'],username:user,credential:btoa(bb)},
      stunGoogle:{urls:'stun:stun.l.google.com:19302'},stunCloudflare:{urls:'stun:stun.cloudflare.com:3478'}};const out={};
    for(const [n,s] of Object.entries(T)){const relay=n.startsWith('stun')?'srflx':'relay';const pc=new RTCPeerConnection({iceServers:[s],iceTransportPolicy:n.startsWith('stun')?'all':'relay'});pc.createDataChannel('x');const got=[];
      pc.onicecandidate=e=>{if(e.candidate&&e.candidate.type)got.push(e.candidate.type);};await pc.setLocalDescription(await pc.createOffer());await new Promise(r=>setTimeout(r,7000));pc.close();out[n]={ok:got.includes(relay),types:[...new Set(got)]};}return out;}).catch(e=>({err:String(e).slice(0,200)}));await p.close();return r;}
// ---- 3. two tablets: A hosts, B looks for the game and joins ----
const ARGS=['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist','--autoplay-policy=no-user-gesture-required'];
async function tablet(tag,block,extra){const args=ARGS.slice();if(block&&block.length)args.push('--host-resolver-rules='+rules(block));const b=await chromium.launch({args});const p=await (await b.newContext({viewport:{width:900,height:640}})).newPage();p.setDefaultTimeout(240000);
  await p.addInitScript(()=>{const W=window.WebSocket;window.__wslog=[];const t0=Date.now();window.WebSocket=function(u,pr){const ws=pr!==undefined?new W(u,pr):new W(u);const tag=/peerjs/.test(u)?'pj:'+(String(u).match(/id=([^&]+)/)||[])[1]:/ntfy/.test(u)?'ntfy':String(u).replace(/^wss?:\/\//,'').slice(0,24);
    const L=(...a)=>{if(window.__wslog.length<160)window.__wslog.push([Math.round((Date.now()-t0)/100)/10,tag,...a]);};L('new');ws.addEventListener('open',()=>L('open'));ws.addEventListener('close',e=>L('close',e.code,String(e.reason||'').slice(0,40)));
    if(/peerjs/.test(u)){ws.addEventListener('message',e=>{let m={};try{m=JSON.parse(e.data);}catch(x){}if(m.type!=='HEARTBEAT')L('msg',m.type||'?',m.payload&&m.payload.msg?String(m.payload.msg).slice(0,40):'');});const s=ws.send.bind(ws);ws.send=d=>{try{const m=JSON.parse(d);if(m.type!=='HEARTBEAT')L('send',m.type,m.dst&&String(m.dst).slice(-6));}catch(x){}return s(d);};}
    return ws;};window.WebSocket.prototype=W.prototype;Object.assign(window.WebSocket,{CONNECTING:0,OPEN:1,CLOSING:2,CLOSED:3});});
  p.errs=[];p.on('pageerror',e=>p.errs.push(e.message.slice(0,200)));await p.goto(BASE+(extra||''),{waitUntil:'commit'});await p.waitForFunction(()=>typeof G!=='undefined'&&G.mode==='title',null,{timeout:300000});
  await p.evaluate(()=>{window.__noAutoQ=true;G.quality='low';});return {b,p};}
const st=p=>p.evaluate(()=>window.__peerRoom&&window.__peerRoom.status?window.__peerRoom.status():null).catch(()=>null);
async function scenario(name,blockA,blockB,extra){const r={name,blockA,blockB};const t0=Date.now();let A,B;
  try{A=await tablet('A',blockA,extra);await A.p.fill('#n0','Hosty');await A.p.click('#bonline');
    r.aLobby=await A.p.waitForFunction(()=>!document.getElementById('bhost').disabled,null,{timeout:60000}).then(()=>Math.round((Date.now()-t0)/1000)).catch(()=>-1);r.aStatus0=await st(A.p);
    if(r.aLobby<0){r.result='A never reached the lobby';return r;}
    await A.p.click('#bhost');r.aHost=await A.p.waitForFunction(()=>NET.role==='host',null,{timeout:40000}).then(()=>true).catch(()=>false);r.aStatus=await st(A.p);
    if(!r.aHost){r.result='A could not host';return r;}
    const t1=Date.now();B=await tablet('B',blockB,extra);await B.p.fill('#n0','Guesty');await B.p.click('#bonline');
    r.bLobby=await B.p.waitForFunction(()=>!document.getElementById('bhost').disabled,null,{timeout:60000}).then(()=>Math.round((Date.now()-t1)/1000)).catch(()=>-1);
    const t2=Date.now();r.bSees=await B.p.waitForSelector('#games button',{timeout:75000}).then(()=>Math.round((Date.now()-t2)/1000)).catch(()=>-1);r.bStatus=await st(B.p);
    if(r.bSees<0){r.bWs=await B.p.evaluate(()=>window.__wslog.slice(0,60)).catch(()=>null);r.aWs=await A.p.evaluate(()=>window.__wslog.slice(0,40)).catch(()=>null);r.result='B did not see the game';return r;}
    await B.p.click('#games button');r.bJoin=await B.p.waitForFunction(()=>NET.role==='guest',null,{timeout:60000}).then(()=>true).catch(()=>false);
    await B.p.waitForTimeout(4000);r.bStatus2=await st(B.p);r.aPeers=await A.p.evaluate(()=>netFriends().length).catch(()=>-1);r.bPeers=await B.p.evaluate(()=>netFriends().length).catch(()=>-1);
    r.aWs=await A.p.evaluate(()=>window.__wslog.filter(x=>String(x[1]).startsWith('pj')).slice(0,40)).catch(()=>null);r.result=r.bJoin&&r.aPeers>0&&r.bPeers>0?'OK ('+((r.bStatus2&&r.bStatus2.lastJoin)||'?')+')':'B saw the game but could not join';}
  catch(e){r.result='error '+String(e).slice(0,200);}
  finally{r.errs=[...(A?A.p.errs:[]),...(B?B.p.errs:[])].slice(0,5);r.secs=Math.round((Date.now()-t0)/1000);try{A&&await A.b.close();}catch(e){}try{B&&await B.b.close();}catch(e){}}return r;}
(async()=>{const all={when:new Date().toISOString(),base:BASE};
  if(!ONLY||ONLY.includes('services')){all.services=await services();log('services',all.services);}
  if(!ONLY||ONLY.includes('pjflap')){all.pjflap=await pjFlap();log('pjflap',all.pjflap);}
  if(!ONLY||ONLY.includes('turn')){const b=await chromium.launch({args:ARGS});all.turn=await turnCheck(b);await b.close();log('turn',all.turn);}
  const ODD=['emqx','hivemq','mosq'],MQALL=['eclipse','emqx','hivemq','shiftr','mosq'];
  const S=[['open',[],[]],['both networks block the odd ports',ODD,ODD],['A blocks odd ports, B has no PeerJS',ODD,['pj']],['only ntfy',['pj',...MQALL],['pj',...MQALL]],
    ['only PeerJS',[...MQALL,'ntfy'],[...MQALL,'ntfy']],['only shiftr',['pj','eclipse','emqx','hivemq','mosq','ntfy'],['pj','eclipse','emqx','hivemq','mosq','ntfy']],['A only PeerJS, B only ntfy (no shared route)',[...MQALL,'ntfy'],['pj',...MQALL]]];
  all.scenarios=[];for(const [n,a,b] of S){if(ONLY&&!ONLY.includes(n)&&!ONLY.includes('scenarios'))continue;const r=await scenario(n,a,b);all.scenarios.push(r);log('scenario',r);}
  fs.writeFileSync(OUT+'/result.json',JSON.stringify(all,null,1));log('DONE');})();
