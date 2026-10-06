const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('app/templates/drafts.html','utf8').match(/async function reanalyzeSavedPhotos[\s\S]+?(?=\nasync function deleteDraft)/)[0];
(async()=>{
  let calls=0,complete,saved=[],messages=[];
  const context={crypto:{randomUUID:()=> 'test-id'},location:{href:''},window:{DraftArchive:{save:async id=>saved.push(id)}},
    showToast:message=>messages.push(message),fetch:async(url,options)=>{calls++;assert.equal(url,'/reanalyze/upload_source');assert.equal(JSON.parse(options.body).request_id,'test-id');return new Promise(resolve=>complete=resolve);}};
  vm.createContext(context);vm.runInContext(source,context);
  const btn={disabled:false,textContent:'Analyse photos again'};
  const first=context.reanalyzeSavedPhotos('upload_source',btn);
  await context.reanalyzeSavedPhotos('upload_source',btn);
  assert.equal(calls,1);assert.equal(btn.disabled,true);
  complete({ok:true,json:async()=>({folder:'upload_new'})});await first;
  assert.equal(context.location.href,'/review/upload_new');assert.deepEqual(saved,['upload_new']);
  context.fetch=async()=>({ok:false,json:async()=>({error:'No saved photos'})});
  context.location.href='';btn.disabled=false;
  await context.reanalyzeSavedPhotos('upload_source',btn);
  assert.equal(context.location.href,'');assert.equal(btn.disabled,false);assert.deepEqual(messages,['No saved photos']);
  console.log('Saved-photo reanalysis prevents duplicate clicks, backs up the new item, opens comparison and surfaces failures');
})().catch(error=>{console.error(error);process.exit(1);});
