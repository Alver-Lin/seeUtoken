/** 基于 archisvaze/liquid-glass 的 SVG 折射滤镜（Chromium 可用；WebKit 走 CSS 回退） */

const SURFACE_FNS = {
  convex_squircle: (x) => Math.pow(1 - Math.pow(1 - x, 4), 0.25),
  lip: (x) => {
    const convex = Math.pow(1 - Math.pow(1 - Math.min(x * 2, 1), 4), 0.25);
    const concave = 1 - Math.sqrt(1 - (1 - x) * (1 - x)) + 0.1;
    const t = 6 * x ** 5 - 15 * x ** 4 + 10 * x ** 3;
    return convex * (1 - t) + concave * t;
  },
};

function calculateRefractionProfile(glassThickness, bezelWidth, heightFn, ior, samples = 128) {
  const eta = 1 / ior;
  function refract(nx, ny) {
    const dot = ny;
    const k = 1 - eta * eta * (1 - dot * dot);
    if (k < 0) return null;
    const sq = Math.sqrt(k);
    return [-(eta * dot + sq) * nx, eta - (eta * dot + sq) * ny];
  }
  const profile = new Float64Array(samples);
  for (let i = 0; i < samples; i++) {
    const x = i / samples;
    const y = heightFn(x);
    const dx = x < 1 ? 0.0001 : -0.0001;
    const y2 = heightFn(x + dx);
    const deriv = (y2 - y) / dx;
    const mag = Math.sqrt(deriv * deriv + 1);
    const ref = refract(-deriv / mag, -1 / mag);
    if (!ref) {
      profile[i] = 0;
      continue;
    }
    profile[i] = ref[0] * ((y * bezelWidth + glassThickness) / ref[1]);
  }
  return profile;
}

function generateDisplacementMap(w, h, radius, bezelWidth, profile, maxDisp) {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  const ctx = c.getContext('2d');
  const img = ctx.createImageData(w, h);
  const d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    d[i] = 128;
    d[i + 1] = 128;
    d[i + 2] = 0;
    d[i + 3] = 255;
  }
  const r = radius;
  const rSq = r * r;
  const r1Sq = (r + 1) ** 2;
  const rBSq = Math.max(r - bezelWidth, 0) ** 2;
  const wB = w - r * 2;
  const hB = h - r * 2;
  const S = profile.length;
  for (let y1 = 0; y1 < h; y1++) {
    for (let x1 = 0; x1 < w; x1++) {
      const x = x1 < r ? x1 - r : x1 >= w - r ? x1 - r - wB : 0;
      const y = y1 < r ? y1 - r : y1 >= h - r ? y1 - r - hB : 0;
      const dSq = x * x + y * y;
      if (dSq > r1Sq || dSq < rBSq) continue;
      const dist = Math.sqrt(dSq);
      const fromSide = r - dist;
      const op =
        dSq < rSq ? 1 : 1 - (dist - Math.sqrt(rSq)) / (Math.sqrt(r1Sq) - Math.sqrt(rSq));
      if (op <= 0 || dist === 0) continue;
      const cos = x / dist;
      const sin = y / dist;
      const bi = Math.min(((fromSide / bezelWidth) * S) | 0, S - 1);
      const disp = profile[bi] || 0;
      const dX = (-cos * disp) / maxDisp;
      const dY = (-sin * disp) / maxDisp;
      const idx = (y1 * w + x1) * 4;
      d[idx] = (128 + dX * 127 * op + 0.5) | 0;
      d[idx + 1] = (128 + dY * 127 * op + 0.5) | 0;
    }
  }
  ctx.putImageData(img, 0, 0);
  return c.toDataURL();
}

function generateSpecularMap(w, h, radius, bezelWidth, angle = Math.PI / 3) {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  const ctx = c.getContext('2d');
  const img = ctx.createImageData(w, h);
  const d = img.data;
  d.fill(0);
  const r = radius;
  const rSq = r * r;
  const r1Sq = (r + 1) ** 2;
  const rBSq = Math.max(r - bezelWidth, 0) ** 2;
  const wB = w - r * 2;
  const hB = h - r * 2;
  const sv = [Math.cos(angle), Math.sin(angle)];
  for (let y1 = 0; y1 < h; y1++) {
    for (let x1 = 0; x1 < w; x1++) {
      const x = x1 < r ? x1 - r : x1 >= w - r ? x1 - r - wB : 0;
      const y = y1 < r ? y1 - r : y1 >= h - r ? y1 - r - hB : 0;
      const dSq = x * x + y * y;
      if (dSq > r1Sq || dSq < rBSq) continue;
      const dist = Math.sqrt(dSq);
      const fromSide = r - dist;
      const op =
        dSq < rSq ? 1 : 1 - (dist - Math.sqrt(rSq)) / (Math.sqrt(r1Sq) - Math.sqrt(rSq));
      if (op <= 0 || dist === 0) continue;
      const cos = x / dist;
      const sin = -y / dist;
      const dot = Math.abs(cos * sv[0] + sin * sv[1]);
      const edge = Math.sqrt(Math.max(0, 1 - (1 - fromSide) ** 2));
      const coeff = dot * edge;
      const col = (255 * coeff) | 0;
      const alpha = (col * coeff * op) | 0;
      const idx = (y1 * w + x1) * 4;
      d[idx] = col;
      d[idx + 1] = col;
      d[idx + 2] = col;
      d[idx + 3] = alpha;
    }
  }
  ctx.putImageData(img, 0, 0);
  return c.toDataURL();
}

function buildFilterMarkup(id, dispUrl, specUrl, blurAmt, scale, specOpacity, specSat) {
  return `
<filter id="${id}" x="-50%" y="-50%" width="200%" height="200%" color-interpolation-filters="sRGB">
  <feImage href="${dispUrl}" result="dispMap"/>
  <feGaussianBlur in="SourceGraphic" stdDeviation="${blurAmt}" result="blurred"/>
  <feDisplacementMap in="blurred" in2="dispMap" scale="${scale}" xChannelSelector="R" yChannelSelector="G" result="displaced"/>
  <feImage href="${specUrl}" result="specMap"/>
  <feColorMatrix in="specMap" type="matrix" values="
    ${specSat} 0 0 0 0
    0 ${specSat} 0 0 0
    0 0 ${specSat} 0 0
    0 0 0 ${specOpacity} 0" result="spec"/>
  <feBlend in="displaced" in2="spec" mode="screen"/>
</filter>`;
}

export function isChromiumBackdrop() {
  const uad = navigator.userAgentData;
  if (uad?.brands?.some((b) => /Chromium/.test(b.brand))) return true;
  return /\bChrome\//.test(navigator.userAgent);
}

/** @param {'standard'|'clear'|'pill'|'panel'} shape */
export function upsertLiquidGlassFilter(filterId, width, height, borderRadius, shape = 'standard') {
  const w = Math.max(2, Math.round(width));
  const h = Math.max(2, Math.round(height));
  const radius = Math.floor(Math.min(borderRadius, w / 2, h / 2));
  const presets = {
    standard: { glassThick: 72, bezel: 48, ior: 2.6, blur: 0.35, specOp: 0.48, specSat: 3.5, scale: 1 },
    clear: { glassThick: 56, bezel: 40, ior: 2.2, blur: 0.25, specOp: 0.55, specSat: 4.2, scale: 0.92 },
    pill: { glassThick: 64, bezel: 52, ior: 2.8, blur: 0.32, specOp: 0.5, specSat: 3.8, scale: 1 },
    panel: { glassThick: 40, bezel: 28, ior: 1.6, blur: 0.55, specOp: 0.22, specSat: 2.2, scale: 0.75 },
  };
  const p = presets[shape] || presets.standard;
  const heightFn =
    shape === 'pill' ? SURFACE_FNS.lip : SURFACE_FNS.convex_squircle;
  const clampedBezel = Math.max(1, Math.min(p.bezel, radius - 1, Math.min(w, h) / 2 - 1));
  const profile = calculateRefractionProfile(p.glassThick, clampedBezel, heightFn, p.ior, 128);
  const maxDisp = Math.max(...Array.from(profile).map(Math.abs), 1e-6);
  const dispUrl = generateDisplacementMap(w, h, radius, clampedBezel, profile, maxDisp);
  const specUrl = generateSpecularMap(w, h, radius, clampedBezel * 2.2);
  const scale = maxDisp * p.scale;
  const markup = buildFilterMarkup(
    filterId,
    dispUrl,
    specUrl,
    p.blur,
    scale,
    p.specOp,
    p.specSat
  );
  let root = document.getElementById('seeu-liquid-svg-defs');
  if (!root) {
    root = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    root.setAttribute('id', 'seeu-liquid-svg-defs');
    root.setAttribute('aria-hidden', 'true');
    root.setAttribute('width', '0');
    root.setAttribute('height', '0');
    root.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden';
    document.body.appendChild(root);
  }
  let defs = root.querySelector('defs');
  if (!defs) {
    defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    root.appendChild(defs);
  }
  const existing = document.getElementById(filterId);
  if (existing) existing.remove();
  const wrapper = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  wrapper.innerHTML = markup;
  const filterEl = wrapper.firstElementChild;
  if (filterEl) defs.appendChild(filterEl);
  return filterId;
}

export function applyLiquidGlassBackdrop(el, filterId) {
  if (!el) return;
  const url = `url(#${filterId})`;
  el.style.setProperty('--lg-backdrop', url);
  el.classList.add('glass-liquid-active');
}

export function clearLiquidGlassBackdrop(el) {
  if (!el) return;
  el.style.removeProperty('--lg-backdrop');
  el.classList.remove('glass-liquid-active');
}
