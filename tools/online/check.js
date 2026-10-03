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
// ---- 2. TURN relays (does a browser get a relay candidate from them?) ----
async function turnCheck(b){const p=await b.newPage();const r=await p.evaluate(async()=>{const user=(Math.floor(Date.now()/1000)+86400)+':bbuddies';const E=new TextEncoder();
    const k=await crypto.subtle.importKey('raw',E.encode('openrelayprojectsecret'),{name:'HMAC',hash:'SHA-1'},false,['sign']);const sg=new Uint8Array(await crypto.subtle.sign('HMAC',k,E.encode(user)));let bb='';for(const x of sg)bb+=String.fromCharCode(x);
    const T={peerjs:{urls:['turn:eu-0.turn.peerjs.com:3478','turn:us-0.turn.peerjs.com:3478'],username:'peerjs',credential:'peerjsp'},openrelay:{urls:['turn:staticauth.openrelay.metered.ca:80','turn:staticauth.openrelay.metered.ca:443','turn:staticauth.openrelay.metered.ca:443?transport=tcp'],username:user,credential:btoa(bb)},
      stunGoogle:{urls:'stun:stun.l.google.com:19302'},stunCloudflare:{urls:'stun:stun.cloudflare.com:3478'}};const out={};
    for(const [n,s] of Object.entries(T)){const relay=n.startsWith('stun')?'srflx':'relay';const pc=new RTCPeerConnection({iceServers:[s],iceTransportPolicy:n.startsWith('stun')?'all':'relay'});pc.createDataChannel('x');const got=[];
      pc.onicecandidate=e=>{if(e.candidate&&e.candidate.type)got.push(e.candidate.type);};await pc.setLocalDescription(await pc.createOffer());await new Promise(r=>setTimeout(r,7000));pc.close();out[n]={ok:got.includes(relay),types:[...new Set(got)]};}return out;}).catch(e=>({err:String(e).slice(0,200)}));await p.close();return r;}
// ---- 3. two tablets: A hosts, B looks for the game and joins ----
const ARGS=['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist','--autoplay-policy=no-user-gesture-required'];
async function tablet(tag,block,extra){const args=ARGS.slice();if(block&&block.length)args.push('--host-resolver-rules='+rules(block));const b=await chromium.launch({args});const p=await (await b.newContext({viewport:{width:900,height:640}})).newPage();p.setDefaultTimeout(240000);
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
    if(r.bSees<0){r.result='B did not see the game';return r;}
    await B.p.click('#games button');r.bJoin=await B.p.waitForFunction(()=>NET.role==='guest',null,{timeout:60000}).then(()=>true).catch(()=>false);
    await B.p.waitForTimeout(4000);r.bStatus2=await st(B.p);r.aPeers=await A.p.evaluate(()=>netFriends().length).catch(()=>-1);r.bPeers=await B.p.evaluate(()=>netFriends().length).catch(()=>-1);
    r.result=r.bJoin&&r.aPeers>0&&r.bPeers>0?'OK ('+((r.bStatus2&&r.bStatus2.lastJoin)||'?')+')':'B saw the game but could not join';}
  catch(e){r.result='error '+String(e).slice(0,200);}
  finally{r.errs=[...(A?A.p.errs:[]),...(B?B.p.errs:[])].slice(0,5);r.secs=Math.round((Date.now()-t0)/1000);try{A&&await A.b.close();}catch(e){}try{B&&await B.b.close();}catch(e){}}return r;}
(async()=>{const all={when:new Date().toISOString(),base:BASE};
  if(!ONLY||ONLY.includes('services')){all.services=await services();log('services',all.services);}
  if(!ONLY||ONLY.includes('turn')){const b=await chromium.launch({args:ARGS});all.turn=await turnCheck(b);await b.close();log('turn',all.turn);}
  const S=[['open',[],[]],['B no PeerJS',[],['pj']],['both only Eclipse+PeerJS',['emqx','hivemq'],['emqx','hivemq']],['A only PeerJS, B only MQTT',['eclipse','emqx','hivemq','shiftr','mosq','ntfy'],['pj']],
    ['A no PeerJS + no Eclipse, B no EMQX/HiveMQ',['pj','eclipse'],['emqx','hivemq']],['only the new routes',['pj','eclipse','emqx','hivemq'],['pj','eclipse','emqx','hivemq']]];
  all.scenarios=[];for(const [n,a,b] of S){if(ONLY&&!ONLY.includes(n)&&!ONLY.includes('scenarios'))continue;const r=await scenario(n,a,b);all.scenarios.push(r);log('scenario',r);}
  fs.writeFileSync(OUT+'/result.json',JSON.stringify(all,null,1));log('DONE');})();
