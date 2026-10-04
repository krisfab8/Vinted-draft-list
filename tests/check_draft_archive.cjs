const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('app/static/draft_archive.js','utf8');
function setup(serverItems, cached, options={}) {
  const state=new Map(cached.map(row=>[row.folder,row]));
  const server=new Map(serverItems.map(folder=>[folder,{folder}]));
  let calls=[], notice={textContent:''},reloads=0;
  const indexedDB={open(){
    const request={};
    queueMicrotask(()=>{
      request.result={transaction(){
        const tx={objectStore(){return {
          getAll(){const r={result:[...state.values()]};queueMicrotask(()=>tx.oncomplete());return r;},
          put(value){const r={};queueMicrotask(()=>{if(options.failWrite){tx.error=Error('Quota');tx.onerror();}else{state.set(value.folder,value);tx.oncomplete();}});return r;}
        };}};return tx;
      }};
      request.onsuccess();
    });return request;
  }};
  const fetch=async (url,opts={})=>{
    calls.push([url,opts.method||'GET']);
    if(url==='/api/listings')return {ok:true,json:async()=>[...server.values()]};
    if(url.startsWith('/api/private/backup?'))return {ok:!options.failBackup,blob:async()=> 'latest:'+url.split('=')[1]};
    if(url==='/api/private/restore-backup'){server.set(opts.body,{folder:opts.body});return {ok:true};}
    if(opts.method==='DELETE'){server.delete(url.split('/')[2]);return {ok:true};}
    if(opts.method==='PATCH')return {ok:true};
    if(url==='/upload')return {ok:true,clone:()=>({json:async()=>({folder:'upload_22222222'})})};
    throw Error('Unexpected URL '+url);
  };
  const ctx={window:{fetch,addEventListener(){}},indexedDB,URL,Promise,Set,Date,location:{origin:'https://app.test',pathname:'/drafts',reload(){reloads++;}},document:{getElementById:()=>notice,addEventListener(){}},queueMicrotask};
  vm.createContext(ctx);vm.runInContext(source,ctx);
  return {ctx,state,server,calls,notice,get reloads(){return reloads;}};
}
(async()=>{
  const existing='upload_11111111',missing='upload_22222222',deleted='upload_33333333';
  const run=setup([existing],[{folder:existing,blob:'old'},{folder:missing,blob:missing},{folder:deleted,deleted:true}]);
  await run.ctx.window.DraftArchive.ready;
  assert(run.server.has(missing));assert(!run.server.has(deleted));assert.equal(run.reloads,1);
  assert.equal(run.calls.filter(([url])=>url.includes('restore-backup')).length,1);
  assert.equal(run.state.get(existing).blob,'latest:'+existing);
  await run.ctx.window.fetch('/listing/'+existing,{method:'PATCH'});await run.ctx.window.DraftArchive.flush();
  await run.ctx.window.fetch('/listing/'+existing,{method:'DELETE'});await run.ctx.window.DraftArchive.flush();
  assert.equal(run.state.get(existing).deleted,true);
  assert(!run.calls.some(([url])=>url.includes('reprice')||url.includes('regen')));
  const quota=setup([existing],[],{failWrite:true});await quota.ctx.window.DraftArchive.ready;
  assert(quota.notice.textContent.includes('unavailable'));assert(!quota.state.has(existing));
  await assert.rejects(quota.ctx.window.fetch('/listing/'+existing,{method:'DELETE'}),/Quota/);
  assert(quota.server.has(existing));assert(quota.notice.textContent.includes('not deleted'));
  assert(!quota.calls.some(([,method])=>method==='DELETE'));
  const failure=setup([existing],[],{failBackup:true});await failure.ctx.window.DraftArchive.ready;
  assert(failure.notice.textContent.includes('unavailable'));assert(!failure.state.has(existing));
  console.log('Archive recovery, server-edit precedence, delete tombstones and failure visibility passed');
})().catch(error=>{console.error(error);process.exit(1)});
