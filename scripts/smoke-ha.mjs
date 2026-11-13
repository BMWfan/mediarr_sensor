// Local-only real-HA command/schema smoke; no provider keys or live media tools.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const base=process.env.HA_SMOKE_URL || 'http://127.0.0.1:8125';
const parsed=new URL(base);
assert.equal(parsed.hostname,'127.0.0.1','This smoke must target disposable loopback HA');
const auth=JSON.parse(await readFile(process.env.HA_SMOKE_AUTH_FILE,'utf8'));
const token=auth.access_token;
assert.ok(token,'Local bootstrap access token required');
const ws=new WebSocket(base.replace('http:','ws:')+'/api/websocket');
const pending=new Map();let next=1;
const timer=setTimeout(()=>{console.error('Real-HA smoke timed out');process.exit(1);},30000);
let readyResolve,readyReject;
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
ws.addEventListener('message',event=>{
 const msg=JSON.parse(event.data);
 if(msg.type==='auth_required')ws.send(JSON.stringify({type:'auth',access_token:token}));
 else if(msg.type==='auth_ok')readyResolve();
 else if(msg.type==='auth_invalid')readyReject(new Error('Local authentication rejected'));
 else if(msg.type==='result'&&pending.has(msg.id)){const {resolve,reject}=pending.get(msg.id);pending.delete(msg.id);msg.success?resolve(msg.result):reject(Object.assign(new Error(msg.error?.code||'command_failed'),{code:msg.error?.code}));}
});
const call=data=>new Promise((resolve,reject)=>{const id=next++;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,...data}));});
try{
 await ready;
 const config=await call({type:'get_config'});
 assert.equal(config.version,'2026.11.1');
 const capabilities=await call({type:'mediarr/request_capabilities'});
 for(const name of ['movie','tv','tmdb','immaculaterr'])assert.equal(capabilities[name].available,false);
 await assert.rejects(call({type:'mediarr/media_details',media_type:'movie',tmdb_id:77}),error=>error.code==='tmdb_not_configured');
 const response=await fetch(base+'/api/config/config_entries/flow',{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify({handler:'mediarr',show_advanced_options:false})});
 assert.equal(response.status,200,'Mediarr config flow must start under actual HA');
 const flow=await response.json();
 try{assert.equal(flow.type,'form');assert.ok(flow.step_id);assert.ok(Array.isArray(flow.data_schema));}
 finally{if(flow.flow_id)await fetch(base+'/api/config/config_entries/flow/'+encodeURIComponent(flow.flow_id),{method:'DELETE',headers:{Authorization:'Bearer '+token}});}
 console.log('PASS: HA 2026.11.1 authenticated Mediarr commands, missing-provider error, disabled capabilities, and actual config-flow schema');
}finally{clearTimeout(timer);ws.close();}
