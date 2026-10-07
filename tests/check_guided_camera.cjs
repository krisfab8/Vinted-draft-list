const fs=require('fs'),vm=require('vm'),assert=require('assert');
const cameraCode=fs.readFileSync('app/static/camera_capture.js','utf8');
const qualityCode=fs.readFileSync('app/static/photo_quality.js','utf8');

// Quality maths: a crisp checkerboard is sharp, a flat grey is not, a dark one asks for light.
{
  const ctx={};vm.createContext(ctx);vm.runInContext(qualityCode,ctx);const Q=ctx.PhotoQuality;
  const img=(f)=>{const a=new Uint8ClampedArray(64*64*4);for(let y=0;y<64;y++)for(let x=0;x<64;x++){const p=(y*64+x)*4;a[p]=a[p+1]=a[p+2]=f(x,y);a[p+3]=255}return a};
  const sharp=Q.grade(Q.measure(img((x,y)=>((x>>2)+(y>>2))%2?220:40),64,64),'label');
  assert(sharp.ok&&sharp.hint==='Sharp');
  const flat=Q.grade(Q.measure(img(()=>128),64,64),'label');
  assert(!flat.ok&&flat.focus==='bad'&&flat.hint==='Move closer');
  const dark=Q.grade(Q.measure(img((x,y)=>((x>>2)+(y>>2))%2?40:10),64,64),'garment');
  assert(!dark.ok&&dark.hint==='More light');
  const glare=Q.grade(Q.measure(img((x,y)=>x<20?255:((x>>2)+(y>>2))%2?200:60),64,64),'label');
  assert(!glare.ok&&glare.hint==='Avoid glare');
  const a=img((x,y)=>((x>>2)+(y>>2))%2?220:40),b=img((x,y)=>((x>>2)+(y>>2)+1)%2?220:40);
  const moved=Q.grade(Q.measure(b,64,64,Q.measure(a,64,64).grey),'label');
  assert(!moved.ok&&moved.hint==='Hold still');
  assert.equal(Q.kindForRole('material'),'label');assert.equal(Q.kindForRole('front'),'garment');
}

function setup(mode){
  const elements={};let files=[],roles=new Map(),notes=new Map(),analysed=0,timer=null,timeouts=[],grade={ok:true,hint:'Sharp',focus:'ok',light:'ok',glare:'ok'};
  function element(){return {hidden:false,disabled:false,textContent:'',innerHTML:'',style:{},dataset:{},children:[],attrs:{},
    classList:{set:new Set(),toggle(k,on){on?this.set.add(k):this.set.delete(k)}},
    setAttribute(k,v){this.attrs[k]=v},addEventListener(k,f){this[k+'Event']=f},append(...n){this.children.push(...n)},appendChild(n){this.children.push(n)},replaceChildren(){this.children=[]},getBBox:()=>({x:44,y:196,width:302,height:375})}}
  for(const id of ['photoCamera','cameraPreview','cameraMessage','cameraNative','cameraTorch','cameraShutter','cameraPhotos','cameraDone','cameraClose','cameraFlip','cameraGallery',
    'cameraGhost','cameraGhostFill','cameraGhostStitch','cameraGhostExtra','cameraStep','cameraExample','cameraExampleArt','cameraDots','cameraSkip','cameraQuality','cameraHint',
    'cameraIntro','cameraLast','cameraReview','cameraReviewImage','cameraReviewTitle','cameraReviewText','cameraReviewRetake','cameraReviewKeep'])elements[id]=element();
  elements.photoCamera.showModal=function(){this.open=true};elements.photoCamera.close=function(){this.open=false};
  elements.cameraPreview.videoWidth=2048;elements.cameraPreview.videoHeight=1536;elements.cameraPreview.play=async()=>{};
  const stream={getTracks:()=>[{stop(){}}],getVideoTracks:()=>[{getSettings:()=>({}),getCapabilities:()=>({})}]};
  const doc={body:{style:{}},hidden:false,getElementById:id=>elements[id],addEventListener(){},createElement(tag){return tag==='canvas'?{getContext:()=>({drawImage(){}}),toBlob:f=>f({size:1})}:element()}};
  const Q={measureSource:()=>({sharpness:1,brightness:1,glare:0,motion:0,grey:[]}),grade:()=>grade};
  const ctx={document:doc,window:{addEventListener(){},PhotoQuality:Q},navigator:{mediaDevices:{getUserMedia:async()=>stream}},
    URL:{createObjectURL:()=>'blob:x',revokeObjectURL(){}},File:class{constructor(p,name){this.name=name}},Date,
    setInterval:f=>{timer=f;return 1},clearInterval:()=>{timer=null},
    setTimeout:(f,ms)=>{const t={f,ms,live:true};timeouts.push(t);return t},clearTimeout:t=>{if(t)t.live=false}};
  vm.createContext(ctx);vm.runInContext(cameraCode,ctx);
  let saved=mode;
  const camera=ctx.createPhotoCamera({getPhotos:()=>files,addPhotos:(inc,role)=>{inc.forEach(f=>roles.set(f,role||'auto'));files.push(...inc)},removePhoto:i=>files.splice(i,1),
    pickGallery(){},pickNativeCamera(){},getMode:()=>saved,setMode:m=>saved=m,getRole:f=>roles.get(f),noteQuality:(f,q)=>notes.set(f,q),getQuality:f=>notes.get(f),onAnalyse:()=>analysed++});
  const click=go=>elements.cameraIntro.clickEvent({target:{closest:()=>({dataset:typeof go==='string'?{go}:go})}});
  const fire=ms=>timeouts.filter(t=>t.live&&t.ms===ms).forEach(t=>{t.live=false;t.f()});
  return {camera,e:elements,files,roles,notes,click,fire,tick:()=>timer&&timer(),setGrade:g=>grade=g,mode:()=>saved,analysed:()=>analysed};
}
const settle=async()=>{for(let i=0;i<10;i++)await Promise.resolve()};
(async()=>{
  // First visit: choose a mode, then the item shape, then the shot list.
  let s=setup('');s.camera.open();
  assert(s.e.cameraIntro.innerHTML.includes('How do you list?'));assert.equal(s.e.cameraIntro.hidden,false);
  s.click({mode:'guided'});assert.equal(s.mode(),'guided');
  s.click('after-mode');assert(s.e.cameraIntro.innerHTML.includes('What is it?'));
  assert(s.e.cameraIntro.innerHTML.includes('Bottoms'));assert(!s.e.cameraIntro.innerHTML.includes('data-go="shots"'));
  s.click({shape:'trousers'});assert(s.e.cameraIntro.innerHTML.includes('5 photos'));  // one tap picks
  s.click('camera');await settle();
  assert.equal(s.e.cameraIntro.hidden,true);assert.equal(s.e.cameraStep.textContent,'Front');
  assert(s.e.cameraGhostFill.attrs.d.startsWith('M110 190'));assert.equal(s.e.cameraSkip.hidden,true);
  // The outline shows the size with a short hint, then fades. Nothing is ever shot automatically.
  assert.equal(s.e.cameraHint.textContent,'Photograph the trousers about this size');
  assert.equal(s.e.cameraGhostFill.attrs.stroke,undefined);
  for(let i=0;i<10;i++)s.tick();assert.equal(s.files.length,0);
  s.fire(2000);assert(s.e.cameraGhost.classList.set.has('faded'));assert.equal(s.e.cameraHint.hidden,true);
  assert.equal(s.e.cameraLast.hidden,true);assert.equal(s.e.cameraGallery.hidden,false);
  await s.e.cameraShutter.onclick();await settle();
  assert.equal(s.files.length,1);assert.equal(s.roles.get(s.files[0]),'front');assert.equal(s.e.cameraStep.textContent,'Back');
  // The photo just taken sits bottom-left; the outline is back for the next step.
  assert.equal(s.e.cameraLast.hidden,false);assert(s.e.cameraLast.innerHTML.includes('<img'));assert.equal(s.e.cameraGallery.hidden,true);
  assert(!s.e.cameraGhost.classList.set.has('faded'));
  // A soft garment shot is kept (flagged) rather than interrupting.
  s.setGrade({ok:false,hint:'Hold still',focus:'bad',light:'ok',glare:'ok'});
  for(let i=0;i<5;i++)s.tick();
  await s.e.cameraShutter.onclick();await settle();
  assert.equal(s.e.cameraReview.hidden,true);assert.equal(s.files.length,2);assert.equal(s.roles.get(s.files[1]),'back');assert.equal(s.notes.get(s.files[1]).ok,false);
  assert.equal(s.e.cameraStep.textContent,'Brand');assert.equal(s.e.cameraSkip.hidden,false);
  assert.equal(s.e.cameraHint.textContent,'Brand label, in focus');
  // Labels wait for focus: pressing while blurry waits, then shoots on the first sharp frame.
  for(let i=0;i<5;i++)s.tick();
  const shot=s.e.cameraShutter.onclick();await settle();
  assert.equal(s.files.length,2);assert.equal(s.e.cameraHint.textContent,'Focusing…');
  s.setGrade({ok:true,hint:'Sharp',focus:'ok',light:'ok',glare:'ok'});s.tick();await shot;await settle();
  assert.equal(s.files.length,3);assert.equal(s.roles.get(s.files[2]),'brand');assert.equal(s.e.cameraStep.textContent,'Size');
  s.e.cameraSkip.onclick();assert.equal(s.e.cameraStep.textContent,'Care label');
  // Still blurry after the wait: the retake screen; Retake keeps nothing, Use anyway keeps it.
  s.setGrade({ok:false,hint:'Move closer',focus:'bad',light:'ok',glare:'ok'});
  for(let i=0;i<5;i++)s.tick();
  let waiting=s.e.cameraShutter.onclick();await settle();s.fire(2500);await waiting;await settle();
  assert.equal(s.e.cameraReview.hidden,false);assert.equal(s.e.cameraReviewTitle.textContent,'Blurry');assert.equal(s.files.length,3);
  s.e.cameraReviewRetake.onclick();assert.equal(s.e.cameraReview.hidden,true);assert.equal(s.files.length,3);
  for(let i=0;i<5;i++)s.tick();
  waiting=s.e.cameraShutter.onclick();await settle();s.fire(2500);await waiting;await settle();s.e.cameraReviewKeep.onclick();
  assert.deepStrictEqual(s.files.map(f=>s.roles.get(f)),['front','back','brand','material']);
  assert(s.e.cameraIntro.innerHTML.includes('All set'));assert(s.e.cameraIntro.innerHTML.includes('ci-photo-flag warn'));
  s.click('flaws');await settle();assert.equal(s.e.cameraStep.textContent,'Flaws');assert.equal(s.e.cameraHint.textContent,'Get close to the flaw');
  await s.e.cameraShutter.onclick();await settle();assert.equal(s.roles.get(s.files[4]),'extra');assert(s.e.cameraIntro.innerHTML.includes('All set'));
  s.click('analyse');assert.equal(s.analysed(),1);assert.equal(s.e.photoCamera.open,false);

  // Pro: straight to the camera, quality dots, never auto-shoots, roles left to the page.
  s=setup('pro');s.camera.open();await settle();
  assert(!s.e.cameraIntro.innerHTML);assert.equal(s.e.cameraQuality.hidden,false);assert.equal(s.e.cameraDone.hidden,false);
  for(let i=0;i<10;i++)s.tick();assert.equal(s.files.length,0);assert(s.e.cameraQuality.innerHTML.includes('class="ok"'));
  await s.e.cameraShutter.onclick();await settle();assert.equal(s.roles.get(s.files[0]),'auto');assert.equal(s.notes.get(s.files[0]).ok,true);
  // Shoes: left, right, sole (an extra slot), size tag, logo; extras advance one at a time.
  s=setup('guided');s.camera.open();s.click({shape:'shoes'});s.click('camera');await settle();
  assert.equal(s.e.cameraStep.textContent,'Left side');assert.equal(s.e.cameraHint.textContent,'Photograph the left side about this size');
  for(const want of ['Right side','Sole','Size tag']){await s.e.cameraShutter.onclick();await settle();assert.equal(s.e.cameraStep.textContent,want);}
  assert.deepStrictEqual(s.files.map(f=>s.roles.get(f)),['front','back','extra']);
  console.log('Photo quality grading, guided steps, fading outline, manual shots, label focus wait, retake, skip, flaws, analyse and pro mode checks passed');
})().catch(e=>{console.error(e);process.exit(1)});
