const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('app/static/item_state.js','utf8');
let revision=1, saves=0, active=0, maxActive=0;
const calls=[];
const nativeFetch=async(url,options={})=>{
  const method=options.method || 'GET';
  calls.push([method,options.headers?.get('If-Match')]);
  if(method!=='GET'){
    active++;maxActive=Math.max(active,maxActive);
    await new Promise(resolve=>setTimeout(resolve,5));
    active--;
    if(options.headers.get('If-Match')!==String(revision))return new Response('{}',{status:409});
    saves++;revision++;
  }
  return new Response('{}',{status:200,headers:{'X-Item-Revision':String(revision)}});
};
function setup(){
  const alerts=[],window={fetch:nativeFetch,alert:message=>alerts.push(message)};
  const ctx={window,location:{origin:'https://app.test'},Headers,URL,Promise};
  vm.createContext(ctx);vm.runInContext(source,ctx);
  return {fetch:window.fetch,alerts};
}
(async()=>{
  const a=setup(),b=setup(),url='/listing/upload_12345678';
  await a.fetch(url);await b.fetch(url);
  const options={method:'PATCH',headers:{'Content-Type':'application/json'},body:'{}'};
  await Promise.all([a.fetch(url,options),a.fetch(url,options)]);
  assert.equal(maxActive,1);assert.equal(saves,2);
  assert.deepEqual(calls.filter(call=>call[0]==='PATCH').map(call=>call[1]),['1','2']);
  await assert.rejects(b.fetch(url,options),/changed in another tab/);
  assert.equal(saves,2);assert.equal(b.alerts.length,1);
  // A conflict cannot silently adopt the newer revision and overwrite on retry.
  await assert.rejects(b.fetch(url,options),/changed in another tab/);
  assert.equal(saves,2);
  await b.fetch(url);await b.fetch(url,options);assert.equal(saves,3);
  console.log('Queued saves, revision headers, stale-tab protection and explicit reload recovery passed');
})().catch(error=>{console.error(error);process.exit(1)});
