// Original procedural art. Three.js 0.180.0 is vendored under its MIT license.
import * as THREE from './vendor/three.module.min.js';
const mount = document.getElementById('stadium');
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
let phase = window.cricinatorPhase || 'home';
try {
  const renderer = new THREE.WebGLRenderer({alpha:true, antialias:true, powerPreference:'low-power'});
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.6));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.35;
  mount.appendChild(renderer.domElement);
  mount.classList.add('webgl-ready');
  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x15323b, .022);
  const camera = new THREE.PerspectiveCamera(40, 1, .1, 150);
  const mat = (color, roughness=.7, metalness=0) => new THREE.MeshStandardMaterial({color,roughness,metalness});
  const grass=mat(0x225c45), gold=mat(0xe9be65,.32,.35), teal=mat(0x148c7b,.45), skin=mat(0xdca979,.65), dark=mat(0x172c39), white=mat(0xf0e9d1);
  function mesh(geometry, material, position, parent=scene) { const m=new THREE.Mesh(geometry,material); m.position.set(...position);parent.add(m);return m; }
  const box=(w,h,d,m,p,parent)=>mesh(new THREE.BoxGeometry(w,h,d),m,p,parent);
  const sphere=(r,m,p,parent)=>mesh(new THREE.SphereGeometry(r,24,16),m,p,parent);
  const cylinder=(r1,r2,h,m,p,parent)=>mesh(new THREE.CylinderGeometry(r1,r2,h,32),m,p,parent);
  scene.add(new THREE.HemisphereLight(0xb1e4eb,0x173c29,2.6));
  const key=new THREE.DirectionalLight(0xffe6be,4);key.position.set(-8,15,12);scene.add(key);
  const rim=new THREE.DirectionalLight(0x83e4d8,3);rim.position.set(10,9,-8);scene.add(rim);
  cylinder(35,35,.4,grass,[0,-.2,-8]);
  for(let i=0;i<9;i++) { const r=new THREE.Mesh(new THREE.RingGeometry(3+i*3.5,4.7+i*3.5,100),mat(i%2?0x20523e:0x2c6548));r.rotation.x=-Math.PI/2;r.position.set(0,.015,-8);scene.add(r); }
  const boundary=mesh(new THREE.TorusGeometry(31,.045,8,128),white,[0,.1,-8]);boundary.rotation.x=Math.PI/2;
  box(3.5,.04,18,mat(0xb1a079),[0,.05,-4]);
  for(const z of [3,-11]) {box(4.8,.025,.045,white,[0,.09,z]);for(let x=-.26;x<.3;x+=.26)cylinder(.032,.032,.8,white,[x,.45,z]);box(.64,.045,.04,gold,[0,.87,z]);}
  // Layered stands and lights establish depth without textures or remote assets.
  for(let tier=0;tier<4;tier++) {
    const stand=mesh(new THREE.TorusGeometry(34+tier*1.5,1.1,4,100),mat([0x243d4c,0x2f4c5a,0x375768,0x456374][tier]),[0,1+tier*1.45,-8]);stand.rotation.x=Math.PI/2;
    for(let j=0;j<90;j++) { const a=j/90*Math.PI*2;const r=34+tier*1.5;sphere(.10,mat(j%3?0x729196:0xdac383),[Math.cos(a)*r,2+tier*1.45,Math.sin(a)*r-8]); }
  }
  const glow=new THREE.MeshBasicMaterial({color:0xf4ffdb});
  for(const [x,z] of [[-23,-25],[22,-26],[-30,4],[30,4]]) {
    cylinder(.15,.25,13,mat(0x71818a,.4,.4),[x,6.5,z]);
    const rig=box(4.5,2,.25,dark,[x,13,z]);rig.lookAt(0,10,5);
    for(let i=0;i<5;i++)for(let j=0;j<2;j++){ const bulb=box(.62,.53,.15,glow,[(i-2)*.82,(j-.5)*.8,.25],rig); }
    const halo=mesh(new THREE.SphereGeometry(1.7,16,12),new THREE.MeshBasicMaterial({color:0xc7ffe9,transparent:true,opacity:.045,depthWrite:false}),[x,13,z]);halo.scale.set(2.6,1.2,1);
  }
  // Scout: an original cricket oracle with a floating ball and scorekeeper coat.
  const host=new THREE.Group();host.position.set(6,0,4);scene.add(host);
  const shadow=mesh(new THREE.CircleGeometry(1.6,48),new THREE.MeshBasicMaterial({color:0x061e20,transparent:true,opacity:.3,depthWrite:false}),[0,.11,0],host);shadow.rotation.x=-Math.PI/2;shadow.scale.y=.65;
  const body=new THREE.Group();host.add(body);
  const coat=cylinder(.63,.91,1.65,teal,[0,2.15,0],body);
  sphere(.64,teal,[0,2.93,0],body).scale.set(1,.55,.8);
  box(.08,1.6,.035,gold,[0,2.15,.66],body);
  for(let y=1.65;y<2.9;y+=.3)sphere(.055,gold,[.18,y,.67],body);
  for(const x of [-.4,.4]) {cylinder(.19,.17,.8,dark,[x,1.03,0],body);const shoe=sphere(.28,dark,[x,.55,.16],body);shoe.scale.set(1,.65,1.7);}
  const head=new THREE.Group();head.position.set(0,3.55,0);body.add(head);
  sphere(.65,skin,[0,0,0],head).scale.set(.95,1.08,.91);
  for(const x of [-.62,.62])sphere(.15,skin,[x,0,0],head);
  const beard=sphere(.54,white,[0,-.33,.19],head);beard.scale.set(1,.8,.72);
  sphere(.105,skin,[0,-.02,.62],head);
  for(const x of [-.23,.23]) {
    sphere(.12,white,[x,.16,.51],head);sphere(.061,dark,[x,.16,.61],head);
    const brow=box(.22,.055,.065,dark,[x,.33,.55],head);brow.rotation.z=x>0?-.12:.12;
    const lens=mesh(new THREE.TorusGeometry(.185,.018,8,24),gold,[x,.16,.64],head);
  }
  box(.1,.025,.035,gold,[0,.18,.65],head);
  const smile=mesh(new THREE.TorusGeometry(.16,.023,8,20,Math.PI),dark,[0,-.25,.60],head);smile.rotation.z=Math.PI;
  cylinder(.74,.75,.13,gold,[0,.61,0],head);
  const cap=sphere(.66,teal,[0,.61,0],head);cap.scale.set(1,.65,1);
  sphere(.09,gold,[0,.77,.58],head);
  const arms=[];
  for(const side of [-1,1]) {
    const arm=new THREE.Group();arm.position.set(side*.62,2.9,0);body.add(arm);
    cylinder(.20,.16,.9,teal,[0,-.37,0],arm);sphere(.19,skin,[0,-.9,0],arm);arm.rotation.z=side*.3;arms.push(arm);
  }
  const cricketBall=sphere(.24,mat(0xc65542,.35),[1.45,3.35,.25],host);
  const seam=mesh(new THREE.TorusGeometry(.242,.008,6,40),white,[0,0,0],cricketBall);seam.rotation.y=.35;
  const orbit=mesh(new THREE.TorusGeometry(.62,.013,6,64),gold,[1.45,3.35,.25],host);orbit.rotation.x=.6;
  const motes=new THREE.Group();scene.add(motes);
  for(let i=0;i<35;i++) { const a=i*2.4; sphere(.025,glow,[Math.sin(a)*14+5,1+(i%9)*.7,Math.cos(a)*10],motes); }
  let frame=0, last=0;
  function resize() {
    const w=mount.clientWidth,h=mount.clientHeight,mobile=w<650;
    renderer.setSize(w,h,false);camera.aspect=w/h;
    camera.position.set(mobile?9:12,mobile?9:8.2,mobile?29:26);
    camera.lookAt(mobile?3:0,mobile?10.5:3,-1);camera.updateProjectionMatrix();
    host.position.set(mobile?4.3:6,mobile?-2.4:0,4);
    host.scale.setScalar(mobile?.82:1.45);
    draw(performance.now());
  }
  function draw(time) {
    const t=reduced.matches?0:time/1000;
    const mobile=mount.clientWidth<650;
    host.position.x = mobile ? 4.3 : phase === "home" ? 7.4 : -3.2;
    host.position.y = 0;
    host.visible = !mobile || phase === "home";
    host.scale.setScalar(mobile ? 1 : phase === "home" ? 1.45 : 1.3);
    body.position.y=.1+Math.sin(t*1.7)*.075;
    body.rotation.y=-.14+Math.sin(t*.45)*.1;
    head.rotation.z=phase==='thinking' ? -.15+Math.sin(t*3)*.06 : phase==='miss' ? .2 : Math.sin(t*.9)*.04;
    arms[0].rotation.z=phase==='complete' ? -2.3+Math.sin(t*5)*.15 : -.25+Math.sin(t*1.5)*.06;
    arms[1].rotation.z=phase==='thinking' ? 1.7 : phase==='complete' ? 2.3+Math.sin(t*5)*.15 : 1.1+Math.sin(t*1.2)*.1;
    cricketBall.position.y=3.4+Math.sin(t*1.7)*.15;
    cricketBall.rotation.z=t*.4;orbit.rotation.z=t*.25;
    if(phase==='guess')orbit.scale.setScalar(1.2+Math.sin(t*3)*.1);else orbit.scale.setScalar(1);
    motes.rotation.y=t*.015;
    renderer.render(scene,camera);
  }
  function loop(time) { frame=0;if(document.hidden||reduced.matches)return;if(time-last>32){draw(time);last=time;}frame=requestAnimationFrame(loop); }
  function run() {cancelAnimationFrame(frame);frame=0;if(!document.hidden){draw(performance.now());if(!reduced.matches)frame=requestAnimationFrame(loop);} }
  document.addEventListener('visibilitychange',run);
  reduced.addEventListener('change',run);
  window.addEventListener('resize',resize);
  window.addEventListener('cricinator-state',e=>{phase=e.detail.phase;draw(performance.now());});
  renderer.domElement.addEventListener('webglcontextlost',e=>{e.preventDefault();cancelAnimationFrame(frame);mount.classList.remove('webgl-ready');renderer.domElement.hidden=true;});
  resize();run();
} catch(error) {
  // The HTML game and designed CSS stadium remain usable without WebGL.
  mount.classList.remove('webgl-ready');
}
