import {PBRMaterial} from '@babylonjs/core/Materials/PBR/pbrMaterial.js';
import {Texture} from '@babylonjs/core/Materials/Textures/texture.js';
import {HDRCubeTexture} from '@babylonjs/core/Materials/Textures/hdrCubeTexture.js';
import {ImageProcessingConfiguration} from '@babylonjs/core/Materials/imageProcessingConfiguration.js';
import {Color3} from '@babylonjs/core/Maths/math.color.js';

/**
 * Local CC0 Poly Haven material/lighting layer. Call after importing the room.
 * It changes no cameras, clinical state, or patient materials. Superseded
 * decorative grain strips are hidden after the scanned wood material loads.
 * All resource failures retain the original material/lighting fallback.
 */
export async function applyClinicalEnvironment(scene, options = {}) {
  const base = options.assetBase || new URL('../assets/polyhaven/', import.meta.url).href;
  const begun = performance.now();
  const report = {version: 'reference-clinic-v1', materials: {}, failures: [], environment: false};
  const resources = [];
  const url = file => new URL(file, base).href;
  function texture(file, data, repeat) {
    return new Promise((resolve, reject) => {
      let timer;
      const tex = new Texture(url(file), scene, false, false, Texture.TRILINEAR_SAMPLINGMODE,
        () => {clearTimeout(timer); resolve(tex);},
        message => {clearTimeout(timer); tex.dispose(); reject(new Error(`${file}: ${message || 'could not load'}`));});
      tex.gammaSpace = !data;
      tex.uScale = repeat;
      tex.vScale = repeat;
      tex.anisotropicFilteringLevel = 4;
      timer = setTimeout(() => {tex.dispose(); reject(new Error(`${file}: texture timed out`));}, 12000);
      resources.push(tex);
    });
  }
  async function material(short, {tint = '#ffffff', repeat = 1, normal = .24} = {}) {
    const maps = await Promise.all([
      texture(`${short}-color.jpg`, false, repeat),
      texture(`${short}-normal.${short==='floor'?'jpg':'png'}`, true, repeat),
      texture(`${short}-orm.${short==='floor'?'jpg':'png'}`, true, repeat),
    ]);
    const mat = new PBRMaterial(`Poly Haven ${short}`, scene);
    mat.albedoColor = Color3.FromHexString(tint).toLinearSpace();
    mat.albedoTexture = maps[0];
    mat.bumpTexture = maps[1];
    mat.bumpTexture.level = normal;
    mat.invertNormalMapX = !scene.useRightHandedSystem;
    mat.invertNormalMapY = scene.useRightHandedSystem;
    mat.metallicTexture = maps[2];
    mat.metallic = 0;
    mat.roughness = 1;
    mat.useRoughnessFromMetallicTextureAlpha = false;
    mat.useRoughnessFromMetallicTextureGreen = true;
    mat.useMetallnessFromMetallicTextureBlue = true;
    mat.useAmbientOcclusionFromMetallicTextureRed = false;
    mat.environmentIntensity = 1;
    resources.push(mat);
    return mat;
  }
  const assignments = [
    ['plaster', {tint: '#e8e2dd', repeat: 1, normal: .022},
      mesh => ['Back wall', 'Left wall', 'Corridor wall', 'Wall above doorway'].includes(mesh.name)],
    ['wood', {tint: '#ffffff', repeat: 1, normal: .16},
      mesh => mesh.name === 'Hinged examination-room door' || /^Cabinet( door(\.\d+)?)?$/.test(mesh.name)],
    ['fabric', {tint: '#ffffff', repeat: 5, normal: .16},
      mesh => ['Folded linen towel', 'Soft pillow'].includes(mesh.name)],
  ];
  const materialTasks = assignments.map(async ([name, settings, match]) => {
    try {
      const mat = await material(name, settings);
      if(name==='plaster'){mat.albedoTexture=null;mat.albedoColor=Color3.FromHexString('#dedbd6').toLinearSpace();}
      const meshes = scene.meshes.filter(match);
      for (const mesh of meshes) mesh.material = mat;
      report.materials[name] = meshes.map(mesh => mesh.name);
      if (name === 'wood') {
        const strips = scene.meshes.filter(mesh =>
          mesh.name === 'Fine door grain' || /^Oak grain detail(\.\d+)?$/.test(mesh.name));
        for (const mesh of strips) mesh.setEnabled(false);
        report.supersededGrainStrips = strips.length;
      }
    } catch (error) {report.failures.push(String(error));}
  });
  const environmentTask = new Promise(resolve => {
    let timer, complete = false;
    function finish(error) {
      if (complete) return;
      complete = true;
      clearTimeout(timer);
      if (error) {
        hdr.dispose();
        report.failures.push(`Studio environment: ${error}`);
        resolve();
        return;
      }
      hdr.rotationY = options.rotationY ?? 1.35;
      scene.environmentTexture = hdr;
      scene.environmentIntensity = options.environmentIntensity ?? .60;
      const image = scene.imageProcessingConfiguration;
      image.toneMappingEnabled = true;
      image.toneMappingType = ImageProcessingConfiguration.TONEMAPPING_ACES;
      image.exposure = options.exposure ?? 1.03;
      image.contrast = 1.06;
      const key = scene.getLightByName('Window light');
      if (key) {
        key.intensity = options.keyIntensity ?? 1.10;
        key.diffuse = new Color3(1, .975, .94);
      }
      const soft = scene.getLightByName('Soft room light');
      if (soft) {
        soft.intensity = .30;
        soft.diffuse = new Color3(.96, .975, 1);
        soft.groundColor = new Color3(.43, .45, .43);
      }
      const fill = scene.getLightByName('Portrait fill');
      if (fill) {
        fill.intensity = .32;
        fill.diffuse = new Color3(1, .985, .97);
      }
      report.environment = true;
      resolve();
    }
    // Linear HDR + spherical harmonics + prefiltered reflections. A 128-pixel
    // cubemap is enough for rough room surfaces and the patient's eye catchlight.
    const hdr = new HDRCubeTexture(url('studio-small-03-1k.hdr'), scene, 128,
      false, true, false, true, () => finish(), message => finish(message || 'load failed'),
      false, false, false, 32);
    resources.push(hdr);
    timer = setTimeout(() => finish('load timed out; original lighting retained'), 12000);
  });
  await Promise.all([...materialTasks, environmentTask]);
  report.readyMs = Math.round(performance.now() - begun);
  report.environmentFaceSize = 128;
  report.source = 'Local Poly Haven Starter Library; CC0-1.0';
  scene.metadata = {...scene.metadata, clinicalEnvironment: report};
  // No eager disposal: the scene owns these resources and releases them normally.
  return report;
}
