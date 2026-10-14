/* ---------- Cast scene: bait drops, a fish loiters, and it strikes when the forecast is ready ---------- */
const CastScene = (() => {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const TIPS = ["Checking river gauges", "Weighing the pressure trend", "Reading the DNR report", "Lining up tides and light", "Checking rules and hours", "Looking through your log", "Asking the fish politely"];
  const MIN_WAIT = 4.2;
  const RIG = 1.8; // rig scale, so the bait reads on a phone // seconds of drop + loitering before a strike can start
  let el = null, cv = null, renderer, scene, camera, raf = 0, clock, ro, alive = false;
  let fish, fishMat, fishW = 1.5, rig, line, lineGeo, bubbles, snow, rays = [], ring;
  let state = "idle", stateT = 0, elapsed = 0, pos = new THREE.Vector3(), vel = new THREE.Vector3(), target = new THREE.Vector3(), facing = 0, faceRot = 0;
  let bait = new THREE.Vector3(0.15, -0.35, 0), rigY = 3.2, pending = null, doneCb = null, verdict = null, shake = 0, tipI = 0, tipT = 0, onStop = null, hooked = false;

  const plateTex = c => { const t = new THREE.CanvasTexture(c); t.minFilter = THREE.LinearFilter; t.needsUpdate = true; return t; };
  function gradTex(stops, w = 4, h = 256, horiz = false) {
    const c = document.createElement("canvas"); c.width = horiz ? 256 : w; c.height = horiz ? w : h;
    const x = c.getContext("2d"), g = horiz ? x.createLinearGradient(0, 0, 256, 0) : x.createLinearGradient(0, 0, 0, h);
    stops.forEach(([o, col]) => g.addColorStop(o, col)); x.fillStyle = g; x.fillRect(0, 0, c.width, c.height); return plateTex(c);
  }
  function dot(r, col) {
    const c = document.createElement("canvas"); c.width = c.height = 64; const x = c.getContext("2d"), g = x.createRadialGradient(32, 32, 0, 32, 32, 32);
    g.addColorStop(0, col); g.addColorStop(r, col.replace(/[\d.]+\)$/, ".35)")); g.addColorStop(1, "rgba(255,255,255,0)"); x.fillStyle = g; x.fillRect(0, 0, 64, 64); return plateTex(c);
  }

  function makeFish() {
    fishMat = new THREE.ShaderMaterial({
      uniforms: { map: { value: null }, uTime: { value: 0 }, uAmp: { value: .07 }, uFreq: { value: 6 }, uHalf: { value: .75 }, uSil: { value: 1 }, uTint: { value: new THREE.Color("#0b2c28") }, uOpacity: { value: .0 } },
      vertexShader: `uniform float uTime,uAmp,uFreq,uHalf;varying vec2 vUv;void main(){vUv=uv;vec3 p=position;float t=clamp((p.x+uHalf)/(2.*uHalf),0.,1.);float w=t*t*1.2+.08;p.z+=sin(t*5.2-uTime*uFreq)*uAmp*w;p.y+=sin(t*3.-uTime*uFreq*.5)*uAmp*.15*w;gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.);}`,
      fragmentShader: `uniform sampler2D map;uniform float uSil,uOpacity;uniform vec3 uTint;varying vec2 vUv;void main(){vec4 c=texture2D(map,vUv);if(c.a<.06)discard;vec3 col=mix(c.rgb*(.78+.32*vUv.y),uTint,uSil);gl_FragColor=vec4(col,c.a*uOpacity);}`,
      transparent: true, side: THREE.DoubleSide, depthWrite: false,
    });
    fish = new THREE.Mesh(new THREE.PlaneGeometry(1, 1, 24, 6), fishMat);
    scene.add(fish);
  }
  async function setFishArt(key, silhouette) {
    let c = null;
    try { const sp = SP[key] || SP["striped-bass"]; c = await plateFor(sp, false); } catch (e) { c = null; }
    if (!c || !alive) return false;
    const old = fishMat.uniforms.map.value; fishMat.uniforms.map.value = plateTex(c); if (old) old.dispose();
    const aspect = c.height / c.width; fishW = key && /catfish|snakehead|gar/.test(key) ? 1.7 : 1.5;
    fish.scale.set(fishW, fishW * aspect, 1); fishMat.uniforms.uHalf.value = .5;
    fishMat.uniforms.uSil.value = silhouette ? .82 : 0;
    return true;
  }

  function makeRig() {
    rig = new THREE.Group();
    const metal = new THREE.MeshStandardMaterial({ color: 0xcfd8d6, metalness: .9, roughness: .25 });
    const lead = new THREE.MeshStandardMaterial({ color: 0x2c3331, metalness: .4, roughness: .6 });
    const sinker = new THREE.Mesh(new THREE.SphereGeometry(.07, 16, 12), lead); sinker.scale.set(.8, 1.25, .8); sinker.position.y = .52; rig.add(sinker);
    const bead = new THREE.Mesh(new THREE.SphereGeometry(.025, 10, 8), new THREE.MeshStandardMaterial({ color: 0xfb7b4b, roughness: .3 })); bead.position.y = .4; rig.add(bead);
    const swivel = new THREE.Mesh(new THREE.TorusGeometry(.022, .008, 6, 12), metal); swivel.position.y = .35; rig.add(swivel);
    const shank = new THREE.Mesh(new THREE.CylinderGeometry(.011, .011, .3, 8), metal); shank.position.y = .02; rig.add(shank);
    const leader = new THREE.Mesh(new THREE.CylinderGeometry(.004, .004, .18, 6), new THREE.MeshBasicMaterial({ color: 0xcfe8e2, transparent: true, opacity: .6 })); leader.position.y = .26; rig.add(leader);
    const bend = new THREE.Mesh(new THREE.TorusGeometry(.075, .011, 8, 24, Math.PI * 1.15), metal); bend.rotation.z = Math.PI * 1.0; bend.position.set(.075, -.13, 0); rig.add(bend);
    const point = new THREE.Mesh(new THREE.ConeGeometry(.016, .06, 8), metal); point.position.set(.15, -.08, 0); rig.add(point);
    const baitMat = new THREE.MeshStandardMaterial({ color: 0xc8566a, roughness: .7, emissive: 0x2a0a0e });
    const chunk = new THREE.Mesh(new THREE.DodecahedronGeometry(.085, 0), baitMat); chunk.scale.set(1.35, .95, .8); chunk.position.set(.07, -.16, 0); chunk.rotation.set(.3, .2, .5); rig.add(chunk);
    const skin = new THREE.Mesh(new THREE.DodecahedronGeometry(.06, 0), new THREE.MeshStandardMaterial({ color: 0xb9c4c8, metalness: .6, roughness: .3 })); skin.scale.set(1.5, .5, .7); skin.position.set(.09, -.1, .03); rig.add(skin);
    rig.scale.setScalar(RIG); scene.add(rig);
    lineGeo = new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute(new Array(3 * 12).fill(0), 3));
    line = new THREE.Line(lineGeo, new THREE.LineBasicMaterial({ color: 0xe8f6f2, transparent: true, opacity: .55 }));
    scene.add(line);
  }

  function build() {
    el = document.createElement("div"); el.className = "castscene";
    el.innerHTML = `<canvas></canvas><div class="cs-cap"><b>Reading the water</b><span class="cs-tip">${TIPS[0]}…</span></div><div class="cs-reel" aria-hidden="true"><svg viewBox="0 0 64 64"><circle cx="32" cy="32" r="27" fill="none" stroke="currentColor" stroke-width="3"/><circle cx="32" cy="32" r="18" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="4 5"/><circle cx="32" cy="32" r="5" fill="currentColor"/><path d="M32 5v10M32 49v10M5 32h10M49 32h10" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></svg><i>zzzZZZ</i></div><button class="cs-stop cap" type="button">Stop</button>`;
    cv = el.querySelector("canvas");
    el.querySelector(".cs-stop").onclick = () => onStop && onStop();
    try { renderer = new THREE.WebGLRenderer({ canvas: cv, antialias: true, alpha: false, powerPreference: "high-performance" }); } catch (e) { renderer = null; return false; }
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
    scene = new THREE.Scene();
    scene.background = gradTex([[0, "#2a6f66"], [.18, "#12403b"], [.55, "#08211f"], [1, "#030a0a"]]);
    scene.fog = new THREE.Fog(0x061716, 4.5, 11);
    camera = new THREE.PerspectiveCamera(40, 1, .1, 50); camera.position.set(0, 0, 6);
    scene.add(new THREE.HemisphereLight(0xbff5ea, 0x05110f, 1.1));
    const sun = new THREE.DirectionalLight(0xffffff, .8); sun.position.set(-1, 4, 3); scene.add(sun);
    // surface band and god rays
    const surf = new THREE.Mesh(new THREE.PlaneGeometry(14, .5), new THREE.MeshBasicMaterial({ map: gradTex([[0, "rgba(200,255,245,0)"], [.5, "rgba(200,255,245,.55)"], [1, "rgba(200,255,245,0)"]]), transparent: true, depthWrite: false }));
    surf.position.set(0, 2.15, -1); scene.add(surf);
    for (let i = 0; i < 5; i++) {
      const r = new THREE.Mesh(new THREE.PlaneGeometry(.5 + Math.random() * .6, 6), new THREE.MeshBasicMaterial({ map: gradTex([[0, "rgba(190,255,240,.22)"], [1, "rgba(190,255,240,0)"]]), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
      r.position.set(-3 + i * 1.5 + Math.random() * .5, 0, -2.5 - Math.random()); r.rotation.z = -.25 + Math.random() * .1; r.userData.ph = Math.random() * 6; scene.add(r); rays.push(r);
    }
    // drifting particles
    const N = 140, sp = new Float32Array(N * 3); for (let i = 0; i < N; i++) { sp[i * 3] = (Math.random() - .5) * 9; sp[i * 3 + 1] = (Math.random() - .5) * 5; sp[i * 3 + 2] = -Math.random() * 4 + 1; }
    snow = new THREE.Points(new THREE.BufferGeometry().setAttribute("position", new THREE.BufferAttribute(sp, 3)), new THREE.PointsMaterial({ size: .035, map: dot(.3, "rgba(220,255,248,.9)"), transparent: true, depthWrite: false, opacity: .55 }));
    scene.add(snow);
    // bubbles
    const B = 40, bp = new Float32Array(B * 3).fill(-99); bubbles = new THREE.Points(new THREE.BufferGeometry().setAttribute("position", new THREE.BufferAttribute(bp, 3)), new THREE.PointsMaterial({ size: .07, map: dot(.55, "rgba(230,255,250,.9)"), transparent: true, depthWrite: false }));
    bubbles.userData.v = new Float32Array(B); scene.add(bubbles);
    // splash ring at the surface
    ring = new THREE.Mesh(new THREE.RingGeometry(.05, .09, 32), new THREE.MeshBasicMaterial({ color: 0xe8fff9, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false }));
    ring.rotation.x = -Math.PI / 2.4; ring.position.set(bait.x, 2.12, 0); scene.add(ring);
    makeRig(); makeFish();
    ro = new ResizeObserver(resize); ro.observe(el);
    return true;
  }
  function resize() {
    if (!renderer || !el) return; const w = el.clientWidth || 360, h = el.clientHeight || 320;
    renderer.setSize(w, h, false); camera.aspect = w / h;
    camera.position.z = w / h < .9 ? 7.2 : 6; camera.updateProjectionMatrix();
  }
  function burst(x, y, n) {
    const p = bubbles.geometry.attributes.position, v = bubbles.userData.v;
    for (let i = 0, k = 0; i < p.count && k < n; i++) if (p.getY(i) < -50 || p.getY(i) > 2.2) { p.setXYZ(i, x + (Math.random() - .5) * .25, y + (Math.random() - .5) * .2, (Math.random() - .5) * .3); v[i] = .5 + Math.random() * .9; k++; }
    p.needsUpdate = true;
  }
  const waypoint = () => target.set(bait.x + (Math.random() < .5 ? -1 : 1) * (1.1 + Math.random() * 1.2), bait.y + (Math.random() - .45) * 1.1, (Math.random() - .5) * .6);
  const mouthOffset = () => (facing === 0 ? 1 : -1) * fishW * .47; // head is the left edge of the plate
  function setState(s) { state = s; stateT = 0; }

  function tick() {
    if (!alive) return;
    raf = requestAnimationFrame(tick);
    const dt = Math.min(clock.getDelta(), .05); elapsed += dt; stateT += dt;
    const T = elapsed; fishMat.uniforms.uTime.value = T;
    rays.forEach(r => { r.material.opacity = .55 + .45 * Math.sin(T * .6 + r.userData.ph); r.rotation.z += Math.sin(T * .2 + r.userData.ph) * .0004; });
    const sp = snow.geometry.attributes.position; for (let i = 0; i < sp.count; i++) { let y = sp.getY(i) + dt * .04; if (y > 2.4) y = -2.4; sp.setY(i, y); sp.setX(i, sp.getX(i) + Math.sin(T * .3 + i) * .0008); } sp.needsUpdate = true;
    const bp = bubbles.geometry.attributes.position, bv = bubbles.userData.v; for (let i = 0; i < bp.count; i++) { const y = bp.getY(i); if (y > -50 && y < 2.3) { bp.setY(i, y + bv[i] * dt); bp.setX(i, bp.getX(i) + Math.sin(T * 4 + i) * .002); } else if (y >= 2.3) bp.setY(i, -99); } bp.needsUpdate = true;
    if (ring.material.opacity > 0) { ring.scale.multiplyScalar(1 + dt * 2.2); ring.material.opacity = Math.max(0, ring.material.opacity - dt * .8); }

    // rig: drop, settle, sway
    if (state === "drop") {
      rigY += (bait.y - rigY) * Math.min(1, dt * (rigY > 2.1 ? 9 : 2.2));
      if (rigY < 2.1 && !rig.userData.splashed) { rig.userData.splashed = true; ring.material.opacity = .8; ring.scale.set(1, 1, 1); burst(bait.x, 2.0, 14); }
      if (Math.random() < .3) burst(bait.x, rigY + .3, 1);
      if (stateT > 1.6) { setState("cruise"); pos.set(bait.x - 3.6, bait.y + .5, -.2); waypoint(); fishMat.uniforms.uOpacity.value = 0; }
    }
    if (!hooked) { rig.position.set(bait.x + Math.sin(T * .9) * .03, rigY + Math.sin(T * 1.3) * .025, 0); rig.rotation.z = Math.sin(T * .7) * .08; }

    // fish behaviour
    const ready = pending && elapsed >= MIN_WAIT;
    if (state !== "drop" && state !== "idle") {
      if (fishMat.uniforms.uOpacity.value < .92 && state !== "gone") fishMat.uniforms.uOpacity.value = Math.min(.92, fishMat.uniforms.uOpacity.value + dt * .6);
      let speed = .55, amp = .07, freq = 6;
      if (ready && verdict !== "SKIP" && ["cruise", "approach", "inspect", "backoff"].includes(state)) { setState("strike"); revealFish(); }
      if (ready && verdict === "SKIP" && ["cruise", "approach", "inspect", "backoff"].includes(state)) { setState("refuse"); }
      if (state === "cruise") { if (pos.distanceTo(target) < .2) { setState("approach"); } }
      if (state === "approach") { const side = pos.x > bait.x ? 1 : -1; target.set(bait.x + side * (fishW * .47 + .32), bait.y - .25, 0); speed = .45; if (pos.distanceTo(target) < .06) setState("inspect"); }
      if (state === "inspect") { speed = .2; amp = .04; target.x += Math.sin(stateT * 5) * .002; if (stateT > 1.1 + Math.random() * .02) { setState("nudge"); } }
      if (state === "nudge") { const side = pos.x > bait.x ? 1 : -1; target.set(bait.x + side * (fishW * .47 + .12), bait.y - .25, 0); speed = .5; if (stateT > .5) { setState("backoff"); waypoint(); } }
      if (state === "backoff") { speed = .7; if (pos.distanceTo(target) < .25 || stateT > 3) { setState("cruise"); waypoint(); } }
      if (state === "strike") { const side = pos.x > bait.x ? 1 : -1; target.set(bait.x + side * fishW * .47, bait.y - .25, 0); speed = 7; amp = .14; freq = 20; if (pos.distanceTo(target) < .08) { hooked = true; shake = .35; burst(bait.x, bait.y, 16); setState("run"); document.querySelector(".castscene")?.classList.add("hot"); } }
      if (state === "run") { speed = 2 + stateT * 7; amp = .16; freq = 24; target.set(bait.x + (facing === 0 ? -6 : 6), 5.5, 0); shake = Math.max(shake, .12); if (Math.random() < .5) burst(pos.x, pos.y, 2); if (pos.y > 3.4 || stateT > 1.6) { setState("gone"); } }
      if (state === "refuse" && stateT < dt * 1.5) { const cap = el.querySelector(".cs-cap"); if (cap) cap.innerHTML = `<b>No takers</b><span class="cs-tip">Nothing worth the drive in this slot</span>`; }
      if (state === "refuse") { const side = pos.x > bait.x ? 1 : -1; if (stateT < .9) { target.set(bait.x + side * (fishW * .47 + .2), bait.y - .1, 0); speed = .5; } else { target.set(bait.x + side * 7, bait.y + .4, -.5); speed = 1.6; } if (stateT > 2.6) setState("gone"); }
      if (state === "gone") { if (stateT > (verdict === "SKIP" ? .2 : .3) && doneCb) { const cb = doneCb; doneCb = null; cb(); return; } }
      // steer
      const d = new THREE.Vector3().subVectors(target, pos), dist = d.length();
      if (dist > 1e-4) { const want = d.multiplyScalar(Math.min(speed, dist / Math.max(dt, 1e-3)) / dist); vel.lerp(want, Math.min(1, dt * (state === "strike" || state === "run" ? 14 : 2.5))); }
      pos.addScaledVector(vel, dt);
      if (Math.abs(vel.x) > .05 && !["inspect", "nudge"].includes(state)) facing = vel.x < 0 ? 0 : Math.PI;
      if (["approach", "inspect", "nudge", "strike"].includes(state)) facing = pos.x > bait.x ? 0 : Math.PI;
      faceRot += (facing - faceRot) * Math.min(1, dt * (state === "strike" ? 18 : 5));
      fish.position.copy(pos); fish.rotation.y = faceRot;
      const climb = Math.atan2(vel.y, Math.abs(vel.x) + .001) * .6; fish.rotation.z = facing === 0 ? -climb : climb;
      fishMat.uniforms.uAmp.value += (amp - fishMat.uniforms.uAmp.value) * dt * 4; fishMat.uniforms.uFreq.value += (freq - fishMat.uniforms.uFreq.value) * dt * 4;
      if (hooked) { rig.position.set(pos.x + (faceRot < Math.PI / 2 ? -fishW * .47 : fishW * .47), pos.y + .2, 0); rig.rotation.z = Math.atan2(vel.y, vel.x) - Math.PI / 2; }
    }
    // line: from above the surface to the sinker, taut when hooked
    const top = new THREE.Vector3(hooked ? bait.x + 1.2 : bait.x, 4, 0), end = new THREE.Vector3(rig.position.x, rig.position.y + .56 * RIG, 0), lp = lineGeo.attributes.position;
    for (let i = 0; i < 12; i++) { const t = i / 11, sag = hooked ? 0 : Math.sin(t * Math.PI) * .06 * Math.sin(T * .8); lp.setXYZ(i, top.x + (end.x - top.x) * t + sag, top.y + (end.y - top.y) * t, 0); }
    lp.needsUpdate = true; lineGeo.computeBoundingSphere();
    // camera
    if (shake > 0) { camera.position.x = (Math.random() - .5) * shake * .3; camera.position.y = (Math.random() - .5) * shake * .3; shake = Math.max(0, shake - dt * .5); } else { camera.position.x = Math.sin(T * .15) * .08; camera.position.y = Math.sin(T * .11) * .05; }
    camera.lookAt(0, -.1, 0);
    // tips
    tipT += dt; if (tipT > 2.4 && state !== "run" && state !== "gone") { tipT = 0; tipI = (tipI + 1) % TIPS.length; const tEl = el.querySelector(".cs-tip"); if (tEl) tEl.textContent = TIPS[tipI] + "…"; }
    renderer.render(scene, camera);
  }
  async function revealFish() {
    const key = pending && pending.play && pending.play.species_key;
    const cap = el.querySelector(".cs-cap"); if (cap) cap.innerHTML = `<b>Fish on!</b><span class="cs-tip">${esc(pending && pending.play ? pending.play.species : "")}</span>`;
    if (key) { const ok = await setFishArt(key, false); if (!ok) fishMat.uniforms.uSil.value = 0; } else fishMat.uniforms.uSil.value = 0;
  }

  return {
    get ok() { return !reduce && typeof THREE !== "undefined"; },
    /** mount the persistent scene element into the given slot (survives page re-renders) */
    mount(slot) { if (el && slot && el.parentNode !== slot) { slot.appendChild(el); resize(); } },
    start(slot, stop) {
      this.stop();
      if (!this.ok || !build()) { el = null; return false; }
      onStop = stop; alive = true; clock = new THREE.Clock(); elapsed = 0; state = "drop"; stateT = 0; rigY = 3.2; hooked = false; pending = null; verdict = null; doneCb = null; shake = 0; tipI = 0; tipT = 0;
      rig.userData.splashed = false; vel.set(0, 0, 0); faceRot = facing = Math.PI;
      setFishArt("striped-bass", true);
      this.mount(slot); tick(); return true;
    },
    /** call when the card is ready; cb runs once the strike (or refusal) finishes */
    finish(card, cb) { if (!alive) { cb(); return; } pending = card; verdict = card.verdict; doneCb = () => { this.stop(); cb(); }; },
    get running() { return alive; },
    stop() {
      alive = false; cancelAnimationFrame(raf); if (ro) ro.disconnect();
      if (renderer) { try { renderer.dispose(); renderer.forceContextLoss(); } catch (e) { } }
      if (scene) scene.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material) { (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => { if (m.map) m.map.dispose(); m.dispose(); }); } });
      if (el && el.parentNode) el.parentNode.removeChild(el);
      renderer = scene = camera = null; el = null; rays = [];
    },
  };
})();
