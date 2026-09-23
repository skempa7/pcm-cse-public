import {MeshBuilder} from '@babylonjs/core/Meshes/meshBuilder.js';
import {TransformNode} from '@babylonjs/core/Meshes/transformNode.js';
import {StandardMaterial} from '@babylonjs/core/Materials/standardMaterial.js';
import {PBRMaterial} from '@babylonjs/core/Materials/PBR/pbrMaterial.js';
import {Texture} from '@babylonjs/core/Materials/Textures/texture.js';
import {DynamicTexture} from '@babylonjs/core/Materials/Textures/dynamicTexture.js';
import {Color3} from '@babylonjs/core/Maths/math.color.js';
import {Vector3} from '@babylonjs/core/Maths/math.vector.js';

/**
 * A project-built examination room (`?env=studio`). Every surface is either
 * geometry made here or a local CC0 Poly Haven map (plaster, wood, fabric);
 * the clock face and the art print are drawn at runtime. Nothing from the
 * supplied room (licenses/SUPPLIED-ROOM.md) is loaded, so pages that must not
 * show that asset -- the Scribbi visit player -- can use this instead.
 *
 * Layout matches the default room: the patient sits at the origin facing +z,
 * the conversation camera is at z ~ 1.7, the back wall is behind her.
 */
const V = (x, y, z) => new Vector3(x, y, z);
const BACK = -2.45, WIDTH = 8.2, HEIGHT = 3.1, DEPTH = 7.4;

export async function createStudioRoom(scene, options = {}) {
  const base = options.assetBase || new URL('../assets/polyhaven/', import.meta.url).href;
  const root = new TransformNode('Studio clinic room', scene);
  const report = {version: 'studio-clinic-v1', meshes: 0, materials: {}, failures: []};
  const receivers = [], casters = [];
  const part = (mesh, {receive = true, cast = false} = {}) => {
    mesh.parent = root; mesh.isPickable = false;
    if (receive) receivers.push(mesh);
    if (cast) casters.push(mesh);
    report.meshes++;
    return mesh;
  };
  const plain = (name, hex, {rough = .8, emissive = null} = {}) => {
    const m = new PBRMaterial(name, scene);
    m.albedoColor = Color3.FromHexString(hex).toLinearSpace();
    m.metallic = 0; m.roughness = rough;
    if (emissive) m.emissiveColor = Color3.FromHexString(emissive).toLinearSpace();
    return m;
  };
  const steel = (() => {const m = plain('Studio brushed steel', '#c9cdd0', {rough: .35}); m.metallic = .85; return m;})();

  // Local CC0 maps; any failure keeps the plain colour already assigned.
  const url = file => new URL(file, base).href;
  function texture(file, data, repeatU, repeatV = repeatU) {
    return new Promise((resolve, reject) => {
      let timer;
      const tex = new Texture(url(file), scene, false, false, Texture.TRILINEAR_SAMPLINGMODE,
        () => {clearTimeout(timer); resolve(tex);},
        message => {clearTimeout(timer); tex.dispose(); reject(new Error(`${file}: ${message || 'could not load'}`));});
      tex.gammaSpace = !data; tex.uScale = repeatU; tex.vScale = repeatV; tex.anisotropicFilteringLevel = 4;
      timer = setTimeout(() => {tex.dispose(); reject(new Error(`${file}: texture timed out`));}, 12000);
    });
  }
  async function textured(mat, short, {repeatU = 1, repeatV = repeatU, normal = .2, useColor = true} = {}) {
    try {
      const [color, bump, orm] = await Promise.all([
        useColor ? texture(`${short}-color.jpg`, false, repeatU, repeatV) : Promise.resolve(null),
        texture(`${short}-normal.png`, true, repeatU, repeatV),
        texture(`${short}-orm.png`, true, repeatU, repeatV),
      ]);
      if (color) mat.albedoTexture = color;
      mat.bumpTexture = bump; mat.bumpTexture.level = normal;
      mat.invertNormalMapX = !scene.useRightHandedSystem;
      mat.invertNormalMapY = scene.useRightHandedSystem;
      mat.metallicTexture = orm; mat.metallic = 0; mat.roughness = 1;
      mat.useRoughnessFromMetallicTextureGreen = true;
      mat.useMetallnessFromMetallicTextureBlue = true;
      mat.useAmbientOcclusionFromMetallicTextureRed = false;
      report.materials[mat.name] = short;
    } catch (error) {report.failures.push(String(error));}
  }

  // ---- shell: floor, two-tone walls, ceiling ----
  const floorMat = plain('Studio oak floor', '#b99a74', {rough: .7});
  const floor = part(MeshBuilder.CreateGround('Studio floor', {width: WIDTH, height: DEPTH}, scene));
  floor.position.z = BACK + DEPTH / 2; floor.material = floorMat;
  const upperMat = plain('Studio wall', '#ecebe5', {rough: .95});
  const lowerMat = plain('Studio wainscot', '#c9d6cf', {rough: .9});
  const railMat = plain('Studio trim', '#f7f6f1', {rough: .6});
  const wall = (name, w, h, pos, rotY, mat) => {
    const p = part(MeshBuilder.CreatePlane(name, {width: w, height: h}, scene));
    p.position = pos; p.rotation.y = rotY; p.material = mat; return p;
  };
  const LOW = 1.02;
  // back wall faces +z (towards the camera)
  wall('Studio back wall', WIDTH, HEIGHT - LOW, V(0, LOW + (HEIGHT - LOW) / 2, BACK), Math.PI, upperMat);
  wall('Studio back wainscot', WIDTH, LOW, V(0, LOW / 2, BACK + .002), Math.PI, lowerMat);
  for (const side of [-1, 1]) {
    const x = side * WIDTH / 2, z = BACK + DEPTH / 2, rot = side < 0 ? -Math.PI / 2 : Math.PI / 2;
    wall(`Studio ${side < 0 ? 'left' : 'right'} wall`, DEPTH, HEIGHT - LOW, V(x, LOW + (HEIGHT - LOW) / 2, z), rot, upperMat);
    wall(`Studio ${side < 0 ? 'left' : 'right'} wainscot`, DEPTH, LOW, V(x - side * .002, LOW / 2, z), rot, lowerMat);
  }
  const ceiling = part(MeshBuilder.CreatePlane('Studio ceiling', {width: WIDTH, height: DEPTH}, scene), {receive: false});
  ceiling.position = V(0, HEIGHT, BACK + DEPTH / 2); ceiling.rotation.x = -Math.PI / 2; ceiling.material = plain('Studio ceiling', '#f4f4f1');
  const panel = part(MeshBuilder.CreatePlane('Studio ceiling light', {width: 1.4, height: .7}, scene), {receive: false});
  panel.position = V(0, HEIGHT - .01, .4); panel.rotation.x = -Math.PI / 2;
  panel.material = plain('Studio light panel', '#ffffff', {emissive: '#fbfaf2'});
  // chair rail and baseboards
  const rail = (name, w, pos, rotY, height = .05, depth = .03) => {
    const b = part(MeshBuilder.CreateBox(name, {width: w, height, depth}, scene), {cast: false});
    b.position = pos; b.rotation.y = rotY; b.material = railMat; return b;
  };
  rail('Studio chair rail', WIDTH, V(0, LOW, BACK + .015), 0);
  rail('Studio back baseboard', WIDTH, V(0, .06, BACK + .015), 0, .12, .025);
  for (const side of [-1, 1]) {
    rail('Studio side chair rail', DEPTH, V(side * (WIDTH / 2 - .015), LOW, BACK + DEPTH / 2), Math.PI / 2);
    rail('Studio side baseboard', DEPTH, V(side * (WIDTH / 2 - .015), .06, BACK + DEPTH / 2), Math.PI / 2, .12, .025);
  }

  // ---- counter, sink and cabinets (back left) ----
  const cabinetMat = plain('Studio cabinet', '#f3f1ea', {rough: .55});
  const topMat = plain('Studio countertop', '#dfe3df', {rough: .35});
  const handleMat = steel;
  const cx = -2.75, cw = 2.3;
  const lowerCabinet = part(MeshBuilder.CreateBox('Studio base cabinet', {width: cw, height: .86, depth: .6}, scene), {cast: true});
  lowerCabinet.position = V(cx, .43, BACK + .3); lowerCabinet.material = cabinetMat;
  const top = part(MeshBuilder.CreateBox('Studio countertop', {width: cw + .04, height: .04, depth: .64}, scene), {cast: true});
  top.position = V(cx, .88, BACK + .32); top.material = topMat;
  for (let i = 0; i < 3; i++) {
    const x = cx - cw / 2 + cw / 6 + i * cw / 3;
    const seam = part(MeshBuilder.CreateBox('Studio door seam', {width: .006, height: .78, depth: .005}, scene), {receive: false});
    seam.position = V(x + cw / 6, .45, BACK + .603); seam.material = railMat;
    const h = part(MeshBuilder.CreateCylinder('Studio handle', {height: .16, diameter: .018}, scene), {receive: false});
    h.position = V(x + cw / 6 - .07, .72, BACK + .62); h.material = handleMat;
  }
  const sink = part(MeshBuilder.CreateBox('Studio sink basin', {width: .55, height: .02, depth: .4}, scene), {receive: false});
  sink.position = V(cx + .35, .901, BACK + .34); sink.material = steel;
  const faucet = part(MeshBuilder.CreateCylinder('Studio faucet', {height: .3, diameter: .03}, scene), {receive: false, cast: true});
  faucet.position = V(cx + .35, 1.05, BACK + .1); faucet.material = steel;
  // Gooseneck: up from the deck, over, and down towards the basin.
  const neck = [];
  for (let i = 0; i <= 16; i++) {const a = i / 16 * Math.PI; neck.push(V(cx + .35, 1.2 + Math.sin(a) * .09, BACK + .1 + (1 - Math.cos(a)) * .09));}
  neck.push(V(cx + .35, 1.13, BACK + .28));
  const spout = part(MeshBuilder.CreateTube('Studio faucet spout', {path: neck, radius: .013, tessellation: 16, cap: 3}, scene), {receive: false, cast: true});
  spout.material = steel;
  const upper = part(MeshBuilder.CreateBox('Studio wall cabinet', {width: cw, height: .7, depth: .34}, scene), {cast: true});
  upper.position = V(cx, 1.95, BACK + .17); upper.material = cabinetMat;
  const dispenser = part(MeshBuilder.CreateBox('Studio sanitizer dispenser', {width: .13, height: .22, depth: .09}, scene), {receive: false, cast: true});
  dispenser.position = V(cx + cw / 2 + .3, 1.25, BACK + .05); dispenser.material = plain('Studio dispenser', '#f7f7f4', {rough: .45});
  const towel = part(MeshBuilder.CreateBox('Studio paper towel holder', {width: .3, height: .32, depth: .11}, scene), {receive: false, cast: true});
  towel.position = V(cx - .45, 1.34, BACK + .06); towel.material = plain('Studio towel holder', '#e9ebe8', {rough: .4});

  // ---- wall diagnostic set (otoscope / ophthalmoscope), right of centre ----
  const diag = part(MeshBuilder.CreateBox('Studio diagnostic panel', {width: .42, height: .26, depth: .06}, scene), {cast: true});
  diag.position = V(1.25, 1.52, BACK + .03); diag.material = plain('Studio diagnostic panel', '#f2f2ef', {rough: .4});
  const headMat = plain('Studio instrument heads', '#2c3438', {rough: .45});
  for (const dx of [-.1, .1]) {
    const handle = part(MeshBuilder.CreateCylinder('Studio instrument handle', {height: .15, diameter: .034}, scene), {receive: false, cast: true});
    handle.position = V(1.25 + dx, 1.44, BACK + .09); handle.material = headMat;
    const head = part(MeshBuilder.CreateBox('Studio instrument head', {width: .05, height: .05, depth: .04}, scene), {receive: false, cast: true});
    head.position = V(1.25 + dx, 1.54, BACK + .1); head.material = headMat;
  }

  // ---- wall clock (drawn face) ----
  const clockTex = new DynamicTexture('Studio clock face', {width: 512, height: 512}, scene, true);
  drawClock(clockTex.getContext(), 512); clockTex.update();
  const clockMat = new StandardMaterial('Studio clock', scene);
  clockMat.diffuseTexture = clockTex; clockMat.specularColor = new Color3(.08, .08, .08); clockMat.emissiveColor = new Color3(.18, .18, .18);
  const clock = part(MeshBuilder.CreateDisc('Studio wall clock', {radius: .19, tessellation: 48}, scene), {receive: false});
  clock.position = V(.35, 2.42, BACK + .03); clock.rotation.y = Math.PI; clock.material = clockMat;
  const rim = part(MeshBuilder.CreateTorus('Studio clock rim', {diameter: .39, thickness: .025, tessellation: 48}, scene), {receive: false, cast: true});
  rim.position = V(.35, 2.42, BACK + .035); rim.rotation.x = Math.PI / 2; rim.material = plain('Studio clock rim', '#3a4441', {rough: .4});

  // ---- framed print (drawn) ----
  const artTex = new DynamicTexture('Studio print', {width: 768, height: 512}, scene, true);
  drawPrint(artTex.getContext(), 768, 512); artTex.update();
  const artMat = new StandardMaterial('Studio print', scene);
  artMat.diffuseTexture = artTex; artMat.specularColor = new Color3(.05, .05, .05); artMat.emissiveColor = new Color3(.16, .16, .16);
  const art = part(MeshBuilder.CreatePlane('Studio framed print', {width: 1.05, height: .7}, scene), {receive: false});
  art.position = V(-1.05, 2.1, BACK + .035); art.rotation.y = Math.PI; art.material = artMat;
  const frameMat = plain('Studio frame', '#6b5a48', {rough: .5});
  for (const [w, h, x, y] of [[1.15, .05, -1.05, 2.475], [1.15, .05, -1.05, 1.725], [.05, .8, -1.6, 2.1], [.05, .8, -.5, 2.1]]) {
    const f = part(MeshBuilder.CreateBox('Studio print frame', {width: w, height: h, depth: .04}, scene), {receive: false, cast: true});
    f.position = V(x, y, BACK + .03); f.material = frameMat;
  }

  // ---- privacy curtain on a ceiling track (right) ----
  const curtainMat = plain('Studio curtain', '#a9bfc6', {rough: .9});
  curtainMat.backFaceCulling = false;
  const paths = [];
  for (const y of [.32, 2.62]) {
    const path = [];
    for (let i = 0; i <= 64; i++) {
      const u = i / 64, x = 2.35 + u * 1.55;
      path.push(V(x, y, BACK + .55 + Math.sin(u * Math.PI * 11) * .045 + u * .25));
    }
    paths.push(path);
  }
  const curtain = part(MeshBuilder.CreateRibbon('Studio privacy curtain', {pathArray: paths, sideOrientation: 2}, scene), {cast: true});
  curtain.material = curtainMat;
  const track = part(MeshBuilder.CreateCylinder('Studio curtain track', {height: 2.1, diameter: .03}, scene), {receive: false});
  track.position = V(3.05, 2.66, BACK + .66); track.rotation.z = Math.PI / 2; track.material = steel;

  const tasks = [
    textured(floorMat, 'wood', {repeatU: 5, repeatV: 4.5, normal: .16}),
    textured(upperMat, 'plaster', {repeatU: 3, repeatV: 1.2, normal: .03, useColor: false}),
    textured(lowerMat, 'plaster', {repeatU: 3, repeatV: .6, normal: .03, useColor: false}),
    textured(curtainMat, 'fabric', {repeatU: 6, repeatV: 5, normal: .22, useColor: false}),
  ];
  await Promise.all(tasks);
  return {
    root,
    report,
    attachShadows(generator) {
      if (!generator) return;
      for (const m of receivers) m.receiveShadows = true;
      for (const m of casters) generator.addShadowCaster(m);
    },
  };
}

function drawClock(ctx, size) {
  const c = size / 2;
  ctx.fillStyle = '#fbfbf8'; ctx.fillRect(0, 0, size, size);
  ctx.save(); ctx.translate(c, c);
  ctx.strokeStyle = '#27302d';
  for (let i = 0; i < 60; i++) {
    const major = i % 5 === 0, a = i / 60 * Math.PI * 2;
    ctx.lineWidth = major ? 12 : 4;
    ctx.beginPath();
    ctx.moveTo(Math.sin(a) * (c * .86), -Math.cos(a) * (c * .86));
    ctx.lineTo(Math.sin(a) * (c * (major ? .70 : .79)), -Math.cos(a) * (c * (major ? .70 : .79)));
    ctx.stroke();
  }
  const hand = (turns, length, width, color) => {
    const a = turns * Math.PI * 2;
    ctx.strokeStyle = color; ctx.lineWidth = width; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(-Math.sin(a) * c * .1, Math.cos(a) * c * .1);
    ctx.lineTo(Math.sin(a) * c * length, -Math.cos(a) * c * length); ctx.stroke();
  };
  hand((10 + 9 / 60) / 12, .48, 16, '#27302d');
  hand(9 / 60, .70, 10, '#27302d');
  hand(34 / 60, .74, 4, '#c0392b');
  ctx.fillStyle = '#27302d'; ctx.beginPath(); ctx.arc(0, 0, 16, 0, Math.PI * 2); ctx.fill();
  ctx.restore();
}

function drawPrint(ctx, w, h) {
  // A calm abstract landscape: layered hills under a pale sky.
  const sky = ctx.createLinearGradient(0, 0, 0, h);
  sky.addColorStop(0, '#e9eef0'); sky.addColorStop(1, '#f6f1e7');
  ctx.fillStyle = sky; ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = '#f2c98f'; ctx.globalAlpha = .9;
  ctx.beginPath(); ctx.arc(w * .72, h * .3, h * .1, 0, Math.PI * 2); ctx.fill();
  ctx.globalAlpha = 1;
  const hill = (y, amp, color, phase) => {
    ctx.fillStyle = color; ctx.beginPath(); ctx.moveTo(0, h);
    for (let x = 0; x <= w; x += 8) ctx.lineTo(x, y + Math.sin(x / w * Math.PI * 2 + phase) * amp + Math.sin(x / w * Math.PI * 5 + phase * 2) * amp * .35);
    ctx.lineTo(w, h); ctx.closePath(); ctx.fill();
  };
  hill(h * .56, h * .06, '#b9cbc3', .4);
  hill(h * .66, h * .07, '#8fae9f', 1.8);
  hill(h * .78, h * .05, '#5f8475', 3.1);
  hill(h * .9, h * .03, '#3f5f55', 4.4);
  ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 18; ctx.strokeRect(9, 9, w - 18, h - 18);
}
