const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('app/templates/index.html','utf8');
const code=source.slice(source.indexOf('  function uploadDimensions'),source.indexOf('  async function createListing'));
let revoked=0,draw,encoded,xhr;
const context={URL:{createObjectURL:()=> 'blob:test',revokeObjectURL:()=>revoked++},
 Image:class {naturalWidth=6000;naturalHeight=4000;async decode(){}},
 File:class {constructor(parts,name,options){this.name=name;this.type=options.type;this.size=parts[0].size}},
 document:{createElement:()=>({getContext:()=>({fillRect(){},drawImage(...args){draw=args.slice(1)}}),toBlob(cb,type,quality){encoded=[type,quality];cb({type,size:300000})}})},
 XMLHttpRequest:class {constructor(){xhr=this;this.upload={}} open(...args){this.openArgs=args} send(form){this.form=form}}
};
vm.createContext(context);vm.runInContext(code,context);
(async()=>{
 assert.deepStrictEqual(Array.from(context.uploadDimensions(6000,4000)),[2048,1365]);
 assert.deepStrictEqual(Array.from(context.uploadDimensions(400,600)),[400,600]);
 const file=await context.prepareUploadPhoto({name:'front.jpeg',type:'image/jpeg',size:6000000});
 assert.strictEqual(file.name,'front.jpg');assert.strictEqual(file.size,300000);
 assert.deepStrictEqual(draw,[0,0,2048,1365]);assert.deepStrictEqual(encoded,['image/jpeg',.85]);assert.strictEqual(revoked,1);
 context.Image=class {async decode(){throw Error('bad photo')}};
 await assert.rejects(context.prepareUploadPhoto({}),/bad photo/);assert.strictEqual(revoked,2);
 const progress=[],form={},promise=context.uploadListingForm(form,t=>progress.push(t));
 assert.deepStrictEqual(xhr.openArgs,['POST','/upload']);assert.strictEqual(xhr.form,form);assert.strictEqual(xhr.timeout,90000);
 xhr.upload.onprogress({lengthComputable:true,loaded:1,total:2});xhr.upload.onload();
 assert.strictEqual(progress[0],'Uploading photos 50%');assert(progress[1].includes('writing'));
 xhr.status=422;xhr.responseText='{"error":"bad"}';xhr.onload();const response=await promise;
 assert.strictEqual(response.ok,false);assert.strictEqual(await response.text(),xhr.responseText);
 const failed=context.uploadListingForm({},()=>{});xhr.ontimeout();await assert.rejects(failed,/Check Drafts before retrying/);
 console.log('Upload compression/progress checks passed');
})().catch(error=>{console.error(error);process.exit(1)});
