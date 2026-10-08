const fs=require('fs'),vm=require('vm'),assert=require('assert');
const code=fs.readFileSync('app/static/camera_capture.js','utf8');
function setup() {
 const elements={},events={},windowEvents={};let files=[],requests=[],stopped=0,revoked=0,draw;
 function element() {return {hidden:false,disabled:false,textContent:'',style:{},children:[],classList:{toggle(){}},setAttribute(k,v){this[k]=v},addEventListener(k,f){this[k+'Event']=f},append(...nodes){this.children.push(...nodes)},appendChild(n){this.children.push(n)},replaceChildren(){this.children=[]}}}
 for(const id of ['photoCamera','cameraPreview','cameraMessage','cameraNative','cameraTorch','cameraShutter','cameraPhotos','cameraDone','cameraClose','cameraFlip','cameraGallery'])elements[id]=element();
 elements.photoCamera.showModal=function(){this.open=true};elements.photoCamera.close=function(){this.open=false;this.closeEvent?.()};
 elements.cameraPreview.videoWidth=2048;elements.cameraPreview.videoHeight=1536;elements.cameraPreview.play=async()=>{};
 const makeStream=()=>({getTracks:()=>[{stop(){stopped++}}],getVideoTracks:()=>[{getSettings:()=>({facingMode:'environment'}),getCapabilities:()=>({torch:true}),applyConstraints:async()=>{}}]});
 let getMedia=async constraints=>{requests.push(constraints);return makeStream()};
 const doc={body:{style:{overflow:'scroll'}},hidden:false,getElementById:id=>elements[id],addEventListener(k,f){events[k]=f},createElement(tag){if(tag==='canvas')return {getContext:()=>({drawImage(...args){draw=args}}),toBlob:f=>f({size:100})};return element()}};
 const ctx={document:doc,window:{addEventListener(k,f){windowEvents[k]=f}},navigator:{mediaDevices:{getUserMedia:c=>getMedia(c)}},URL:{createObjectURL:()=> 'blob:photo',revokeObjectURL(){revoked++}},File:class{constructor(parts,name,options){this.name=name;this.type=options.type}},Date};
 vm.createContext(ctx);vm.runInContext(code,ctx);
 let gallery=0,native=0;
 const camera=ctx.createPhotoCamera({getPhotos:()=>files,addPhotos:incoming=>files.push(...incoming),removePhoto:i=>files.splice(i,1),pickGallery:()=>gallery++,pickNativeCamera:()=>native++});
 return {camera,e:elements,doc,events,windowEvents,makeStream,media:f=>getMedia=f,files,requests,stats:()=>({stopped,revoked,draw,gallery,native})};
}
const settle=async()=>{for(let i=0;i<10;i++)await Promise.resolve()};
(async()=>{
 let s=setup();s.camera.open();await settle();
 assert.equal(s.e.photoCamera.open,true);assert.equal(s.requests[0].audio,false);assert.equal(s.requests[0].video.width.ideal,2048);assert(!s.e.cameraShutter.disabled);
 await s.e.cameraShutter.onclick();assert.equal(s.files.length,1);assert.equal(s.files[0].type,'image/jpeg');assert.equal(s.e.cameraDone.textContent,'Done · 1');assert.equal(s.e.cameraPhotos.children.length,1);
 s.e.cameraGallery.onclick();assert.equal(s.stats().gallery,1);
 s.e.cameraFlip.onclick();await settle();assert.equal(s.requests[1].video.facingMode.ideal,'user');assert.equal(s.stats().stopped,1);
 s.e.cameraPhotos.children[0].onclick();assert.equal(s.files.length,0);
 s.doc.hidden=true;s.events.visibilitychange();assert(s.e.cameraShutter.disabled);s.doc.hidden=false;s.events.visibilitychange();await settle();assert.equal(s.requests.length,3);
 s.camera.close();assert.equal(s.doc.body.style.overflow,'scroll');assert(!s.e.photoCamera.open);assert.equal(s.stats().stopped,3);
 // Permission denied offers working native/gallery fallbacks.
 s=setup();s.media(async()=>{const err=Error();err.name='NotAllowedError';throw err});s.camera.open();await settle();assert(!s.e.cameraNative.hidden);assert(s.e.cameraMessage.textContent.includes('Camera is blocked'));assert.equal(s.e.cameraRetry?.hidden??false,false);assert(s.e.cameraShutter.disabled);s.e.cameraNative.onclick();assert.equal(s.stats().native,1);s.camera.close();
 // Closing before permission resolution must release the late stream.
 s=setup();let resolve;s.media(()=>new Promise(r=>resolve=r));s.camera.open();s.camera.close();resolve(s.makeStream());await settle();assert.equal(s.stats().stopped,1);assert.equal(s.e.cameraPreview.srcObject,null);
 // Encoding completed after close must not add a photo.
 s=setup();s.camera.open();await settle();let encode;s.doc.createElement=()=>({getContext:()=>({drawImage(){}}),toBlob:f=>encode=f});const pending=s.e.cameraShutter.onclick();s.camera.close();encode({size:100});await pending;assert.equal(s.files.length,0);
 // Stop on page exit and enforce the shared twenty-photo ceiling.
 s=setup();s.camera.open();await settle();for(let i=0;i<20;i++)s.files.push({});s.camera.refresh();assert(s.e.cameraShutter.disabled);await s.e.cameraShutter.onclick();assert.equal(s.files.length,20);s.windowEvents.pagehide();assert.equal(s.stats().stopped,1);
 console.log('Live camera lifecycle, capture, switching, permission fallback, stale requests and limit checks passed');
})().catch(e=>{console.error(e);process.exit(1)});
