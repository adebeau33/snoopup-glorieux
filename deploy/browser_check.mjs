import {spawn} from 'node:child_process';
import fs from 'node:fs';
const chrome=spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',['--headless','--disable-gpu','--no-sandbox','--remote-debugging-port=9223','--user-data-dir='+process.cwd()+'/.browser-preview','about:blank'],{stdio:'ignore'});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
try{
 let tabs;
 for(let n=0;n<30;n++){try{tabs=await(await fetch('http://127.0.0.1:9223/json')).json();break;}catch{await sleep(200);}}
 const ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);await new Promise(r=>ws.addEventListener('open',r,{once:true}));
 let seq=0;const pending=new Map();ws.addEventListener('message',e=>{const msg=JSON.parse(e.data);if(msg.id&&pending.has(msg.id)){pending.get(msg.id)(msg);pending.delete(msg.id);}});
 const call=(method,params={})=>new Promise(resolve=>{const id=++seq;pending.set(id,resolve);ws.send(JSON.stringify({id,method,params}));});
 await call('Emulation.setDeviceMetricsOverride',{width:390,height:1000,deviceScaleFactor:1,mobile:true});
 for(const [path,name] of [['/inscription/','signup'],['/','home'],['/evenement/premiere-soiree-21-novembre-2026/','event']]){
  await call('Page.navigate',{url:'https://glorieux.snoopup.io'+path});await sleep(1800);
  const result=await call('Runtime.evaluate',{expression:"JSON.stringify({width:innerWidth,scroll:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+2).slice(0,8).map(e=>({tag:e.tagName,cls:e.className,width:e.getBoundingClientRect().width}))})",returnByValue:true});
  console.log(path,result.result.result.value);
  if(name==='signup'){const eye=await call('Runtime.evaluate',{expression:`(()=>{const fields=[...document.querySelectorAll('input[type=password]')];if(fields.length!==2)return false;for(const input of fields){const button=input.parentNode.querySelector('.password-toggle');if(!button)return false;input.value='UnMotDePasseDeTest123!';button.click();if(input.type!=='text'||button.getAttribute('aria-pressed')!=='true')return false;button.click();if(input.type!=='password'||input.value!=='UnMotDePasseDeTest123!')return false;input.value='';}return true;})()`,returnByValue:true});if(eye.result.result.value!==true)throw new Error('Password visibility check failed');console.log('Boutons œil : affichage/masquage vérifié sur les deux champs.');}
  const image=await call('Page.captureScreenshot',{format:'png'});fs.writeFileSync('output/mobile-'+name+'.png',Buffer.from(image.result.data,'base64'));
 }
 ws.close();
}finally{chrome.kill();}
