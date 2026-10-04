const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('app/templates/index.html','utf8');
let calls=[];
const ctx={WeakMap,Promise,prepareUploadPhoto:async f=>{
  calls.push(f); await Promise.resolve(); return {prepared:f};
}};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('  const preparedPhotos'),source.indexOf('  function uploadDimensions')),ctx);
(async()=>{
  const a={},b={};
  const p=ctx.queuePhotoPreparation(a);
  assert.strictEqual(p,ctx.queuePhotoPreparation(a));
  const q=ctx.queuePhotoPreparation(b);
  await Promise.all([p,q]);
  assert.deepStrictEqual(calls,[a,b]);
  assert.strictEqual(await p,await ctx.queuePhotoPreparation(a));
  ctx.prepareUploadPhoto=async()=>{throw Error('bad photo')};
  await assert.rejects(ctx.queuePhotoPreparation({}),/bad photo/);
  ctx.prepareUploadPhoto=async f=>f;
  const next={};
  assert.strictEqual(await ctx.queuePhotoPreparation(next),next);
  assert(source.includes('incoming.forEach(file => queuePhotoPreparation(file))'));
  assert(source.includes('await queuePhotoPreparation(uploadPhotos[i])'));
  console.log('Photo pre-preparation, reuse and failure recovery checks passed');
})().catch(e=>{console.error(e);process.exit(1)});
