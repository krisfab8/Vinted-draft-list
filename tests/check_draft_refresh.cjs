const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('app/templates/drafts.html','utf8');
const source=html.match(/<script>([\s\S]*?)<\/script>/)[1]
  .replace(/\{\{ listings \| tojson \}\}/,JSON.stringify([{folder:'upload_11111111',description:'old'}, {folder:'upload_22222222',description:'old second'}]));
const calls=[],pending=[],rendered=[],messages=[];
const context={document:{addEventListener(){}},Date,FormData,fetch:async(url,opts)=>{
  calls.push([url,opts]);return await new Promise(resolve=>pending.push(resolve));
}};
vm.createContext(context);vm.runInContext(source,context);
context.renderSheet=index=>rendered.push(vm.runInContext(`LISTINGS[${index}].description`,context));
context.showToast=message=>messages.push(message);
(async()=>{
 const first=context.openSheet(0);
 assert.equal(calls[0][1].cache,'no-store');
 assert(calls[0][0].includes('?fresh='));
 pending.shift()({ok:true,json:async()=>({folder:'upload_11111111',description:'new size lines'})});
 await first;assert.deepEqual(rendered,['new size lines']);
 const slow=context.openSheet(0),fast=context.openSheet(1);
 const a=pending.shift(),b=pending.shift();
 b({ok:true,json:async()=>({folder:'upload_22222222',description:'latest second'})});await fast;
 a({ok:true,json:async()=>({folder:'upload_11111111',description:'late wrong sheet'})});await slow;
 assert.deepEqual(rendered,['new size lines','latest second']);
 const failure=context.openSheet(0);pending.shift()({ok:false});await failure;
 assert.equal(rendered.length,2);assert(messages[0].includes('latest draft'));
 // Deleting a card must not shift indices embedded in the surviving cards.
 context.confirm=()=>true;
 let removed=false;
 context.document.getElementById=()=>({remove(){removed=true;}});
 context.document.querySelector=()=>null;
 context.closeSheet=()=>{};
 const deletion=context.deleteDraft({stopPropagation(){}},'upload_11111111',{textContent:'Delete listing',disabled:false});
 pending.shift()({ok:true});await deletion;assert(removed);
 const next=context.openSheet(1);
 assert(calls.at(-1)[0].includes('upload_22222222'));
 pending.shift()({ok:true,json:async()=>({folder:'upload_22222222',description:'correct surviving item'})});
 await next;assert.equal(rendered.at(-1),'correct surviving item');
 console.log('Fresh loading, racing requests and card identity after deletion passed');
})().catch(error=>{console.error(error);process.exit(1)});
