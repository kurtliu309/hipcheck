// hipcheck film: one continuous GSAP timeline, sampled frame by frame.
// createFilm(root, lang) -> { frame(t), destroy() }. frame(t) is deterministic for any t, in any order.
import gsap from "gsap";

export const TOTAL = 59;
let OFFSET = 0;

const L = {
  en: {
    wheel: ["Missing files.", "Missing caches.", "Absolute paths.", "D:/ paths.", "//server paths.", "Floating nodes.", "Unused nodes.", "Dead branches."],
    w1: "Missing files.", w2: "Absolute paths.", w3: "Floating nodes.", w4: "Dead branches.", w5: 'One <span class="a">click.</span>',
    t1: "Broken paths and dead nodes. Found in one click.",
    lf: "Floating", lu: "Unused branch", li: "Ignored · saved in the .hip",
    nf: "Not flagged", nf1: "Defaults", nf2: "Render outputs", nf3: "$HIP paths",
    k1: "<em>●</em>Display flag", k2: "<em>●</em>OUT_*", k3: "<em>●</em>File writers", k4: "<em>●</em>Locked · commented", k5: "<em>●</em>Referenced",
    o1: "Also runs on 20.5", o2h: "One JSON", o2: "Drop it in packages", o3: "Every change, one undo", o4: "Tests pass in hython",
    kOpen: "Open", kCheck: "Check", kClean: "Clean", kJump: "Jump", kDelete: "Delete", kUndo: "Undo", kIgnore: "Ignore", kKeep: "Keep",
    s1: "A week of work leaves stray nodes and broken paths.",
    s2: "One click on the hipcheck shelf opens the window and scans.",
    s3: "Input files that don't exist. Paths typed as D:/ or //server.",
    s4: "Click a row. The node lights up in the network.",
    s5: "Defaults, render outputs and $HIP paths are left alone.",
    s6: "Nodes whose result never reaches anything that matters.",
    s7: "Color them red. Look before you delete.",
    s8: "Double-click a row to frame its node.",
    s9: "It rescans, then asks. Only nodes still unused go.",
    s10: "Ctrl+Z brings everything back in one step.",
    s11: "Keep a stray node on purpose. The mark is saved with the hip.",
    s12: "Anything that feeds these is never listed.",
    scn: ["OPEN", "CHECK", "CLEAN", "DELETE", "IGNORE", "KEEP", "INSTALL"],
  },
  zh: {
    wheel: ["丢失的文件。", "丢失的缓存。", "写死的路径。", "D:/ 路径。", "//server 路径。", "散落的节点。", "没用的节点。", "无用的分支。"],
    w1: "丢失的文件。", w2: "写死的路径。", w3: "散落的节点。", w4: "无用的分支。", w5: '一键<span class="a">搞定。</span>',
    t1: "坏路径和无用节点，一键找出。",
    lf: "散落", lu: "无用分支", li: "已忽略 · 存在 hip 里",
    nf: "不报", nf1: "默认值", nf2: "渲染输出", nf3: "$HIP 路径",
    k1: "<em>●</em>显示标志", k2: "<em>●</em>OUT_*", k3: "<em>●</em>写文件节点", k4: "<em>●</em>锁定 · 带注释", k5: "<em>●</em>被引用",
    o1: "20.5 也能跑", o2h: "一个 JSON", o2: "放进 packages 就行", o3: "每次改动都能撤销", o4: "hython 测试全过",
    kOpen: "打开", kCheck: "Check", kClean: "Clean", kJump: "跳转", kDelete: "删除", kUndo: "撤销", kIgnore: "忽略", kKeep: "保留",
    s1: "干了一周，留下散落的节点和坏掉的路径。",
    s2: "在 hipcheck 工具架上点一下，窗口打开并扫描。",
    s3: "不存在的输入文件；写成 D:/ 或 //server 的路径。",
    s4: "点一行，网络里对应的节点就亮起来。",
    s5: "默认值、渲染输出和 $HIP 路径一律不报。",
    s6: "结果流不到任何有用地方的节点。",
    s7: "先标红，看清楚再删。",
    s8: "双击一行，直接框住节点。",
    s9: "先重扫，再确认，只删仍然无用的。",
    s10: "Ctrl+Z 一步全部恢复。",
    s11: "故意留下的节点就忽略它，标记跟着 hip 保存。",
    s12: "流向这些的节点，永远不会被列出。",
    scn: ["打开", "CHECK", "CLEAN", "删除", "忽略", "保留", "安装"],
  },
};

const NODES = {
  file_rock: [230, 62, "#f2c75c"], file_tree: [400, 62, "#f2c75c"], transform1: [230, 145, "#7fb6ec"],
  smooth1: [70, 228, "#8fdc95"], merge1: [300, 228, "#b994ef"], color1: [70, 318, "#ff9a72"], OUT_geo: [300, 318, "#f1f3f5"],
  box1: [520, 145, "#6c93d6"], mountain1: [520, 228, "#b38a63"], ctrl: [520, 330, "#f1f3f5"],
};
const WIRES = [["file_rock", "transform1", 48], ["transform1", "merge1", 30], ["file_tree", "merge1", 66], ["merge1", "OUT_geo", 48],
  ["transform1", "smooth1", 48], ["smooth1", "color1", 48], ["box1", "mountain1", 48]];
const ALL = Object.keys(NODES);
const ROWS = ["c0", "c1", "c2", "k-float", "k-box1", "k-mountain1", "k-unused", "k-smooth1", "k-color1"];
const DEAD = ["box1", "mountain1", "smooth1", "color1"];
const KROWS = ["k-float", "k-box1", "k-mountain1", "k-unused", "k-smooth1", "k-color1"];
const KSEL = KROWS.map((r) => "#" + r).join(",");
const TRANSITION_WINDOW = 0.7; // longest CSS transition in film.css is 0.5s

export function createFilm(root, lang) {
  const $ = (id) => root.querySelector("#" + id);
  const tr = (k) => L[lang][k];
  const stage = $("stage");

  /* ---------- build ---------- */
  let w = "";
  for (const [a, b, ix] of WIRES) {
    const [x1, y1] = NODES[a], [x2, y2] = NODES[b], sx = x1 + 48, sy = y1 + 33, ex = x2 + ix, ey = y2 - 3, my = (sy + ey) / 2;
    w += `<path class="wire" data-a="${a}" data-b="${b}" d="M${sx} ${sy} C${sx} ${my} ${ex} ${my} ${ex} ${ey}"/>`;
  }
  $("wires").innerHTML = w;
  let h = "";
  for (const [n, [x, y, c]] of Object.entries(NODES)) {
    h += `<div class="nsh" id="s-${n}" style="left:${x}px;top:${y + 12}px"></div>
      <div class="nd" id="n-${n}" style="left:${x}px;top:${y}px"><i class="ring"></i><div class="nb"><i class="sl"></i><i class="dot" style="background:${c}"></i><i class="sr ${n === "OUT_geo" ? "disp" : ""}"></i></div>${n === "file_tree" ? '<i class="err">!</i>' : ""}<span class="lbl">${n}</span></div>`;
  }
  $("nodes").innerHTML = h;
  root.querySelectorAll(".jmp").forEach((j) => (j.innerHTML = '<svg viewBox="0 0 12 12"><path d="M2 10L10 2M5 2h5v5" stroke="#d5dade" stroke-width="1.6" fill="none" stroke-linecap="round"/></svg>'));
  $("logo").innerHTML = [..."hipcheck"].map((c, i) => `<span class="${i >= 3 ? "a" : ""}">${c}</span>`).join("");
  root.querySelectorAll("[data-i18n]").forEach((el) => (el.innerHTML = tr(el.dataset.i18n)));
  const WORDS = [...tr("wheel"), tr("w5")];
  $("drum").innerHTML = WORDS.map((w) => `<div class="wi">${w}</div>`).join("");

  /* pointer targets in surface-local layout coordinates (transform-proof) */
  const POS = {};
  const rel = (id, surface) => {
    let el = $(id), x = 0, y = 0;
    const w0 = el.offsetWidth, h0 = el.offsetHeight;
    while (el && el !== surface) { x += el.offsetLeft; y += el.offsetTop; el = el.offsetParent; }
    return { x, y, w: w0, h: h0 };
  };
  ["tab-clean", "c0", "c1", "b-sa", "b-color", "b-ign", "b-del", "k-color1", "k-box1", "k-mountain1", "k-smooth1", "k-float", "s-ok"].forEach((id) => (POS[id] = rel(id, $("card"))));
  POS["dock-hc"] = rel("dock-hc", $("dock"));

  /* ---------- discrete state (classes, text) ---------- */
  const D = [], BASE = new Map(), LAST = new Map();
  const defOf = (k) => { const [kind, id, cls] = k.split("|"); if (kind === "c") return $(id).classList.contains(cls); if (kind === "t") return $(id).textContent; return null; };
  const at = (t, pairs) => { for (const [k] of pairs) if (!BASE.has(k)) BASE.set(k, defOf(k)); D.push([t, pairs]); };
  const C = (id, cls, on = true) => ["c|" + id + "|" + cls, on], TX = (id, v) => ["t|" + id, v];
  const ND = (ns, cls, on = true) => ns.map((n) => C("n-" + n, cls, on));
  const clr = () => [...ND(ALL, "sel", false), ...ROWS.map((r) => C(r, "sel", false))];
  const applyKey = (k, v) => {
    if (LAST.get(k) === v) return; LAST.set(k, v);
    const [kind, id, cls] = k.split("|");
    if (kind === "c") $(id).classList.toggle(cls, v);
    else if (kind === "t") $(id).textContent = v;
    else if (k === "ck") $("ck").textContent = v ? tr(v) : "";
    else if (k === "cs") $("cs").textContent = v ? tr(v) : "";
    else if (k === "scn") $("scn").textContent = String(v + 1).padStart(2, "0") + " — " + tr("scn")[v];
  };
  const stateAt = (t) => { const m = new Map(BASE); for (const [tt, p] of D) { if (tt > t) break; for (const [k, v] of p) m.set(k, v); } return m; };

  /* ---------- timeline ---------- */
  const tl = gsap.timeline({ paused: true });
  // music sync: hit(t, kind) asks for film time t to land on a beat ('beat'), a bar ('bar') or beat index n
  const ANCHORS = [], SFX = [], CHAPTERS = []; // CHAPTERS: [filmTime, key] for players that jump between sections
  const hit = (t, kind) => ANCHORS.push([t, kind]);
  const sfx = (t, name, vol = 1) => SFX.push([t, name, vol]);
  // moves start with some speed and spend their time decelerating: no wind-up, so cuts between moves never feel like a stop
  const bez = (x1, y1, x2, y2) => (x) => {
    let lo = 0, hi = 1, t = x;
    for (let k = 0; k < 24; k++) { t = (lo + hi) / 2; const bx = 3 * (1 - t) ** 2 * t * x1 + 3 * (1 - t) * t * t * x2 + t ** 3; if (bx < x) lo = t; else hi = t; }
    return 3 * (1 - t) ** 2 * t * y1 + 3 * (1 - t) * t * t * y2 + t ** 3;
  };
  const SM = bez(0.25, 0.1, 0.1, 1), SO = "power3.out";
  let capPos = { x: 64, y: 540 };
  function cap(t, k, s, pos) {
    const move = pos && (pos.x !== capPos.x || pos.y !== capPos.y);
    tl.to("#capb", { opacity: 0, y: -6, duration: 0.28, ease: "power2.in" }, t - 0.28);
    at(t, [["ck", k], ["cs", s]]);
    if (move) { tl.to("#capw", { x: pos.x, y: pos.y, duration: 1.1, ease: SM }, t - 0.3); capPos = pos; }
    const pt = t + (move ? 0.5 : 0.02);
    tl.fromTo("#capb", { opacity: 0, y: 14, scale: 0.96 }, { opacity: 1, y: 0, scale: 1, duration: 0.5, ease: SO, immediateRender: false }, pt);
    hit(pt, "beat"); sfx(pt, "pop", 0.55);
  }
  function sub(t, s) {
    tl.to("#cs", { opacity: 0, duration: 0.22, ease: "power2.in" }, t - 0.22);
    at(t, [["cs", s]]);
    tl.to("#cs", { opacity: 1, duration: 0.4, ease: SO }, t + 0.02);
  }
  const ptrState = { pc: { x: 200, y: 200 }, pd: { x: 20, y: 20 } };
  function ptrTo(p, id, t, d = 0.6, min = 0.5) {
    const r = POS[id], pad = 5, box = { x: r.x - pad, y: r.y - pad, w: r.w + pad * 2, h: r.h + pad * 2 };
    const dist = Math.hypot(box.x - ptrState[p].x, box.y - ptrState[p].y), dd = Math.max(min, Math.min(0.9, d * (0.6 + dist / 500)));
    tl.to("#" + p, { x: box.x, y: box.y, width: box.w, height: box.h, borderRadius: Math.min(box.h / 2, 16), backgroundColor: "rgba(255,255,255,0.16)", boxShadow: "0 0 0 1px rgba(255,255,255,.22)", duration: dd, ease: SM }, t);
    ptrState[p] = box; return t + dd;
  }
  function ptrFree(p, x, y, t, d = 0.5) {
    tl.to("#" + p, { x: x - 11, y: y - 11, width: 22, height: 22, borderRadius: 11, backgroundColor: "rgba(255,255,255,0.82)", boxShadow: "0 2px 10px rgba(0,0,0,.5)", duration: d, ease: SM }, t);
    ptrState[p] = { x: x - 11, y: y - 11 };
  }
  function press(p, t, target) {
    sfx(t, "click", 0.5);
    tl.to("#" + p, { scale: 0.92, duration: 0.09, ease: "power2.in", transformOrigin: "50% 50%" }, t).to("#" + p, { scale: 1, duration: 0.24, ease: "back.out(3)" }, t + 0.09);
    if (target) {
      tl.to("#" + target, { scale: 0.94, duration: 0.09, ease: "power2.in" }, t).to("#" + target, { scale: 1, duration: 0.26, ease: "back.out(3)" }, t + 0.09);
      at(t, [C(target, "down")]); at(t + 0.2, [C(target, "down", false)]);
    }
  }
  function rise(ns, t, z = 70, d = 0.9, st = 0.07) {
    ns.forEach((n, i) => {
      tl.to("#n-" + n, { z, duration: d, ease: "expo.out" }, t + i * st);
      tl.to("#s-" + n, { opacity: z > 0 ? 0.9 : 0, scale: z > 0 ? 1.3 : 1, y: z > 0 ? 22 : 0, duration: d, ease: "expo.out" }, t + i * st);
    });
  }
  const B = {
    open: { x: 0, y: 20, z: 0, rotationX: 26, rotationY: 0, rotationZ: -7, scale: 1, opacity: 1 },
    back: { x: -170, y: 10, z: -140, rotationX: 18, rotationY: 18, rotationZ: -3, scale: 1, opacity: 1 },
    deep: { x: -230, y: 0, z: -320, rotationX: 16, rotationY: 24, rotationZ: -2, scale: 1, opacity: 1 },
    front: { x: -20, y: 40, z: 60, rotationX: 34, rotationY: -2, rotationZ: -6, scale: 1, opacity: 1 },
    zoom: { x: 302, y: -180, z: 320, rotationX: 10, rotationY: 0, rotationZ: 0, scale: 1, opacity: 1 },
    keep: { x: -210, y: 30, z: 20, rotationX: 28, rotationY: 12, rotationZ: -5, scale: 1, opacity: 1 },
    gone: { x: -60, y: 120, z: -1300, rotationX: 52, rotationY: 0, rotationZ: -10, scale: 1, opacity: 0 },
  };
  const K = {
    side: { x: -40, y: 0, z: 70, rotationX: 0, rotationY: -14, scale: 1, opacity: 1 },
    front: { x: -110, y: 0, z: 200, rotationX: 0, rotationY: -8, scale: 1, opacity: 1 },
    away: { x: 300, y: 20, z: -460, rotationX: 0, rotationY: -38, scale: 1, opacity: 0 },
    del: { x: -60, y: 0, z: 150, rotationX: 0, rotationY: -8, scale: 1, opacity: 1 },
  };
  let lastWhoosh = -9;
  const mv = (sel, pose, t, d = 1.6, ease = SM) => {
    if (d >= 1.5 && Math.abs(t - lastWhoosh) > 0.6) { sfx(t + 0.05, "whoosh", 0.35); lastWhoosh = t; }
    return tl.to(sel, { ...pose, duration: d, ease }, t);
  };

  gsap.set("#board", { ...B.gone, y: 200 });
  gsap.set("#card", { x: -290, y: -290, z: 0, scale: 0.12, rotationX: -20, opacity: 0 });
  gsap.set("#dock", { y: -40, z: -120, rotationX: -24, opacity: 0 });
  gsap.set("#keys", { y: 260, z: 60, rotationX: 64, opacity: 0 });
  gsap.set("#sheet", { yPercent: 130 });
  gsap.set(".nd", { z: 160, opacity: 0 });
  gsap.set(".row", { opacity: 0, x: 24 });
  gsap.set("#pc", { x: 200, y: 200 }); gsap.set("#pd", { x: 20, y: 20 });
  gsap.set("#capw", { x: 64, y: 540 });
  gsap.set("#logo", { transformOrigin: "50% 50%" });

  /* ambient light + camera rig: long overlapping moves so the frame never sits still */
  tl.to("#g1", { x: 300, y: -200, duration: TOTAL, ease: "sine.inOut" }, 0);
  tl.to("#g2", { x: -320, y: 140, duration: TOTAL, ease: "sine.inOut" }, 0);
  const R = [[0, { rotationY: -6, rotationX: 2, x: 0, y: 0 }], [5, { rotationY: 4, rotationX: -1, x: 10, y: -6 }], [12, { rotationY: -3, rotationX: 2, x: -10, y: 4 }],
    [20, { rotationY: 5, rotationX: -2, x: 10, y: -4 }], [30, { rotationY: -4, rotationX: 1, x: -6, y: 2 }], [38, { rotationY: 3, rotationX: -1, x: 6, y: 0 }],
    [43, { rotationY: -5, rotationX: 2, x: -10, y: 6 }], [50, { rotationY: 2, rotationX: 6, x: 0, y: -20 }]];
  gsap.set("#rig", R[0][1]);
  for (let i = 1; i < R.length; i++) { const t1 = R[i + 1] ? R[i + 1][0] : TOTAL; tl.to("#rig", { ...R[i][1], duration: t1 - R[i][0] + 1.5, ease: "sine.inOut" }, R[i][0] - 1.5); }

  /* COLD OPEN */
  at(0, [["scn", 0], ["ck", null], ["cs", null]]); CHAPTERS.push([0, "intro"]);
  gsap.set("#veil", { opacity: 1 }); // black from the very first frame
  // picker wheel: words sit on a drum and click into place on the beat
  const STEP = 24, RAD = 360;
  root.querySelectorAll(".wi").forEach((el, i) => (el.style.transform = `rotateX(${-i * STEP}deg) translateZ(${RAD}px)`));
  gsap.set("#drum", { z: -RAD, rotationX: -STEP * 0.7 });
  tl.to("#wheel", { opacity: 1, duration: 0.3, ease: "power2.out" }, 0.1);
  // one continuous glide, already moving when it appears, decelerating onto "One click." on the beat; ticks as each word passes center
  const NW = WORDS.length - 1, G0 = 0.1, G1 = 2.9, A0 = -STEP * 2.2, A1 = NW * STEP, GE = "power2.out", gease = gsap.parseEase(GE);
  gsap.set("#drum", { rotationX: A0 });
  tl.to("#drum", { rotationX: A1, duration: G1 - G0, ease: GE }, G0);
  hit(G1, "beat");
  for (let i = 0; i <= NW; i++) {
    let lo = 0, hi = 1; const goal = (i * STEP - A0) / (A1 - A0);
    for (let k = 0; k < 40; k++) { const mid = (lo + hi) / 2; if (gease(mid) < goal) lo = mid; else hi = mid; }
    sfx(G0 + lo * (G1 - G0) - (i === NW ? 0.02 : 0), "tick", i === NW ? 0.8 : 0.45);
  }
  tl.to("#drum", { rotationX: "+=" + STEP * 1.2, duration: 0.4, ease: "power2.in" }, 3.2);
  tl.to("#wheel", { opacity: 0, scale: 0.97, duration: 0.36, ease: "power2.in" }, 3.22);
  tl.set("#logo", { opacity: 1 }, 3.4); hit(3.4, "beat"); sfx(3.4, "shimmer", 0.5);
  tl.from("#logo span", { yPercent: 115, duration: 0.9, ease: "expo.out", stagger: 0.035 }, 3.4);
  tl.fromTo("#tag1", { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.7, ease: SO, immediateRender: false }, 3.85);
  tl.to("#tag1", { opacity: 0, y: -8, duration: 0.35, ease: "power2.in" }, 4.95);
  tl.to("#logo", { x: -528, y: -282, scale: 0.17, duration: 1.3, ease: SM }, 5.05);
  tl.to("#veil", { opacity: 0, duration: 1.4, ease: "power2.inOut" }, 5.5); hit(5.5, "bar");
  mv("#board", B.open, 5.5, 2.2, "power3.out");
  tl.to(".nd", { z: 0, opacity: 1, duration: 1, ease: "expo.out", stagger: 0.06 }, 6.2);

  /* OPEN */
  CHAPTERS.push([5.4, "kOpen"]);
  cap(7.0, "kOpen", "s1", { x: 64, y: 540 });
  tl.to("#dock", { y: 0, z: 0, rotationX: 0, opacity: 1, duration: 1.1, ease: SO }, 8.2);
  tl.fromTo("#pd", { opacity: 0 }, { opacity: 1, duration: 0.3, immediateRender: false }, 8.9);
  let e = ptrTo("pd", "dock-hc", 9.0, 0.7); press("pd", e + 0.05, "dock-hc");
  sub(e + 0.1, "s2");
  const op = e + 0.3;
  tl.to("#pd", { opacity: 0, duration: 0.2 }, op);
  tl.to("#dock", { x: 190, y: 150, z: -60, scale: 0.5, rotationX: 20, opacity: 0, duration: 0.9, ease: "power3.in" }, op);
  mv("#card", K.side, op + 0.1, 1.6, "expo.out");
  mv("#board", B.back, op, 1.8);

  /* CHECK */
  at(11.6, [["scn", 1]]); CHAPTERS.push([11.4, "kCheck"]); hit(11.6, "bar");
  mv("#card", K.front, 11.6, 1.8); mv("#board", B.deep, 11.6, 1.8);
  cap(12.4, "kCheck", "s3", { x: 64, y: 92 });
  tl.to("#c0,#c1,#c2", { opacity: 1, x: 0, duration: 0.7, ease: "expo.out", stagger: 0.12 }, 12.6);
  tl.fromTo("#pc", { opacity: 0 }, { opacity: 1, duration: 0.3, immediateRender: false }, 13.7);
  ptrFree("pc", 300, 330, 13.6, 0.01);
  e = ptrTo("pc", "c0", 13.8); press("pc", e + 0.05);
  at(e + 0.1, [...clr(), C("c0", "sel"), ...ND(["file_tree"], "sel")]); sub(e + 0.15, "s4");
  tl.fromTo("#n-file_tree", { z: 0 }, { z: 44, duration: 0.45, ease: "power2.out", yoyo: true, repeat: 1, immediateRender: false }, e + 0.1);
  e = ptrTo("pc", "c1", e + 1.3); press("pc", e + 0.05);
  at(e + 0.1, [...clr(), C("c1", "sel"), ...ND(["file_rock"], "sel")]);
  tl.fromTo("#n-file_rock", { z: 0 }, { z: 44, duration: 0.45, ease: "power2.out", yoyo: true, repeat: 1, immediateRender: false }, e + 0.1);
  sub(17.2, "s5");
  tl.to("#nf .t", { opacity: 1, duration: 0.4 }, 17.3);
  tl.fromTo("#nf .pill", { opacity: 0, y: 14, scale: 0.92 }, { opacity: 1, y: 0, scale: 1, duration: 0.55, ease: "back.out(2)", stagger: 0.1, immediateRender: false }, 17.4);
  tl.to("#nf .t,#nf .pill", { opacity: 0, y: 8, duration: 0.4, stagger: 0.04 }, 19.3);
  tl.to("#pc", { opacity: 0, duration: 0.3 }, 19.2);

  /* CLEAN */
  at(19.6, [["scn", 2], ...clr()]); CHAPTERS.push([19.4, "kClean"]); hit(19.6, "bar");
  mv("#card", K.away, 19.6, 1.8); mv("#board", B.front, 19.6, 2);
  cap(20.6, "kClean", "s6", { x: 820, y: 60 });
  rise(["box1", "mountain1"], 21.3, 80); rise(["smooth1", "color1"], 21.6, 80);
  at(21.3, ND(["box1", "mountain1"], "fl-float")); at(21.6, ND(["smooth1", "color1"], "fl-unused"));
  tl.fromTo("#lab-float", { opacity: 0, z: 40 }, { opacity: 1, z: 120, duration: 0.7, ease: "expo.out", immediateRender: false }, 21.6);
  tl.fromTo("#lab-unused", { opacity: 0, z: 40 }, { opacity: 1, z: 120, duration: 0.7, ease: "expo.out", immediateRender: false }, 21.9);
  tl.to("#lab-float,#lab-unused", { opacity: 0, z: 60, duration: 0.5 }, 23.5);
  mv("#board", B.back, 23.5, 1.8); mv("#card", K.side, 23.6, 1.8);
  tl.to("#thumb", { xPercent: 100, duration: 0.6, ease: "expo.out" }, 24.4); sfx(24.4, "click", 0.4);
  at(24.45, [C("tab-check", "on", false), C("tab-clean", "on")]);
  tl.to("#pg-check", { opacity: 0, duration: 0.25 }, 24.4); tl.to("#pg-clean", { opacity: 1, duration: 0.3 }, 24.5);
  tl.to(KSEL, { opacity: 1, x: 0, duration: 0.55, ease: "expo.out", stagger: 0.06 }, 24.5);
  cap(24.6, "kClean", "s7", { x: 64, y: 540 });
  tl.to("#pc", { opacity: 1, duration: 0.3 }, 25.0); ptrFree("pc", 220, 300, 24.9, 0.01);
  e = ptrTo("pc", "b-sa", 25.1); press("pc", e + 0.05, "b-sa");
  at(e + 0.1, [...KROWS.map((r) => C(r, "sel")), ...ND(DEAD, "sel")]);
  e = ptrTo("pc", "b-color", e + 0.5); press("pc", e + 0.05, "b-color");
  at(e + 0.12, [...ND(DEAD, "red"), ...ND(DEAD, "sel", false)]);
  /* JUMP: click rows on the right, the board refocuses on each node, faster and faster */
  // pose that brings node n to a screen spot left of the card, board scaled up
  const focus = (n) => {
    const [nx, ny] = NODES[n], k = 1.35, tx = 390, ty = 400;
    return { x: tx - 580 - (nx + 48 - 360) * k, y: ty - 360 - (ny + 15 - 210) * k, z: 0, rotationX: 10, rotationY: 6, rotationZ: -2, scale: k, opacity: 1 };
  };
  const ROWNODE = { "k-box1": "box1", "k-mountain1": "mountain1", "k-smooth1": "smooth1", "k-color1": "color1" };
  const jt0 = e + 0.55; CHAPTERS.push([jt0 - 0.3, "kJump"]);
  cap(jt0, "kJump", "s8", { x: 64, y: 92 });
  mv("#card", { x: -70, y: 0, z: 150, rotationX: 0, rotationY: -12, scale: 1, opacity: 1 }, jt0 - 0.1, 1.1);
  let jt = jt0 + 0.2, gap = 0.95;
  for (const r of ["k-box1", "k-smooth1", "k-mountain1", "k-box1", "k-color1"]) {
    e = ptrTo("pc", r, jt, gap * 0.45, 0.16); press("pc", e + 0.02);
    at(e + 0.06, [...clr(), C(r, "sel"), ...ND([ROWNODE[r]], "sel")]);
    tl.to("#board", { ...focus(ROWNODE[r]), duration: Math.max(0.32, gap * 0.95), ease: SM }, e + 0.03);
    jt = e + gap * 0.42; gap *= 0.8;
  }
  jt = e + 0.7; // let the last focus settle on color1
  tl.to("#pc", { opacity: 0, duration: 0.25 }, jt - 0.2);

  const o = Math.max(0, jt + 0.1 - 30); // the delete section starts right after the jump
  OFFSET = o;
  /* DELETE + UNDO */
  at(o + 30, [["scn", 3]]); CHAPTERS.push([o + 29.8, "kDelete"]); hit(o + 30, "bar");
  mv("#board", B.back, o + 30, 1.9); mv("#card", K.del, o + 30.1, 1.8);
  cap(o + 30.8, "kDelete", "s9", { x: 64, y: 540 });
  at(o + 31, [...clr(), ...KROWS.map((r) => C(r, "sel")), ...ND(DEAD, "sel")]);
  tl.to("#pc", { opacity: 1, duration: 0.3 }, o + 31.6); ptrFree("pc", 200, 250, o + 31.5, 0.01);
  e = ptrTo("pc", "b-del", o + 31.7); press("pc", e + 0.05, "b-del");
  tl.to("#sheet", { yPercent: 0, duration: 0.7, ease: "expo.out" }, e + 0.15); sfx(e + 0.12, "swoosh_up", 0.45);
  e = ptrTo("pc", "s-ok", e + 0.75, 0.45); press("pc", e + 0.05, "s-ok");
  const del = e + 0.2;
  sfx(del + 0.08, "delete", 0.75);
  tl.to("#sheet", { yPercent: 130, duration: 0.55, ease: "power3.in" }, del);
  tl.to("#pc", { opacity: 0, duration: 0.25 }, del);
  DEAD.forEach((n, i) => {
    tl.to("#n-" + n, { z: -240, opacity: 0, duration: 0.7, ease: "power3.in" }, del + 0.1 + i * 0.08);
    tl.to("#s-" + n, { opacity: 0, duration: 0.4 }, del + 0.1 + i * 0.08);
    tl.to(`.wire[data-a="${n}"],.wire[data-b="${n}"]`, { opacity: 0, duration: 0.5 }, del + 0.15 + i * 0.08);
  });
  tl.to(KSEL, { height: 0, marginBottom: 0, opacity: 0, duration: 0.5, ease: "power3.inOut", stagger: 0.04 }, del + 0.1);
  tl.to("#k-empty", { opacity: 1, duration: 0.4 }, del + 0.6);
  at(del + 0.1, [TX("nk", "0"), ...clr()]);
  const un = del + 1.1;
  cap(un + 0.2, "kUndo", "s10", { x: 64, y: 540 });
  tl.to("#board", { z: "-=160", rotationX: "+=6", duration: 1.2, ease: SM }, un);
  tl.to("#card", { z: "-=160", duration: 1.2, ease: SM }, un);
  tl.to("#keys", { y: 0, z: 180, rotationX: 30, opacity: 1, duration: 1.1, ease: "expo.out" }, un + 0.1);
  const kp = un + 1.05;
  sfx(kp, "key", 0.8); sfx(kp + 0.1, "key", 0.8);
  tl.to("#key-c", { y: 12, boxShadow: "inset 0 2px 0 #fff,0 2px 0 #9aa1a8,0 12px 24px #000b", duration: 0.1 }, kp);
  tl.to("#key-z", { y: 12, boxShadow: "inset 0 2px 0 #fff,0 2px 0 #9aa1a8,0 12px 24px #000b", duration: 0.1 }, kp + 0.1);
  tl.to("#key-c,#key-z", { y: 0, boxShadow: "inset 0 2px 0 #fff,0 14px 0 #9aa1a8,0 30px 50px #000b", duration: 0.3, ease: "back.out(3)" }, kp + 0.32);
  tl.to("#keys", { y: 280, z: 60, rotationX: 64, opacity: 0, duration: 1, ease: "power3.in" }, kp + 0.55);
  tl.to("#board", { z: "+=160", rotationX: "-=6", duration: 1.3, ease: SM }, kp + 0.6);
  tl.to("#card", { z: "+=160", duration: 1.3, ease: SM }, kp + 0.6);
  const bk = kp + 0.4;
  sfx(bk, "restore", 0.5);
  DEAD.forEach((n, i) => {
    tl.to("#n-" + n, { z: 80, opacity: 1, duration: 0.8, ease: "back.out(1.6)" }, bk + i * 0.08);
    tl.to("#s-" + n, { opacity: 0.9, duration: 0.5 }, bk + i * 0.08);
    tl.to(`.wire[data-a="${n}"],.wire[data-b="${n}"]`, { opacity: 1, duration: 0.5 }, bk + 0.1 + i * 0.08);
  });
  tl.to("#k-empty", { opacity: 0, duration: 0.25 }, bk);
  tl.to(KSEL, { height: (i, el) => (el.classList.contains("grp") ? 30 : 42), marginBottom: (i, el) => (el.classList.contains("grp") ? 2 : 7), opacity: 1, duration: 0.55, ease: "expo.out", stagger: 0.05 }, bk + 0.05);
  at(bk, [TX("nk", "4")]);

  /* IGNORE */
  at(o + 38, [["scn", 4]]); CHAPTERS.push([o + 37.8, "kIgnore"]); hit(o + 38, "bar");
  tl.to("#card", { ...K.side, duration: 2, ease: SM }, o + 38);
  cap(o + 38.4, "kIgnore", "s11", { x: 64, y: 92 });
  tl.to("#pc", { opacity: 1, duration: 0.3 }, o + 38.9); ptrFree("pc", 220, 330, o + 38.8, 0.01);
  e = ptrTo("pc", "k-float", o + 39.0); press("pc", e + 0.05);
  at(e + 0.1, [...clr(), C("k-float", "sel"), C("k-box1", "sel"), C("k-mountain1", "sel"), ...ND(["box1", "mountain1"], "sel")]);
  e = ptrTo("pc", "b-ign", e + 0.5); press("pc", e + 0.05, "b-ign");
  const ig = e + 0.15;
  sfx(ig, "swoosh_up", 0.35); sfx(ig + 0.4, "blip2", 0.4);
  tl.to("#k-float,#k-box1,#k-mountain1", { height: 0, marginBottom: 0, opacity: 0, duration: 0.5, ease: "power3.inOut", stagger: 0.05 }, ig);
  at(ig, [...clr(), ...ND(["box1", "mountain1"], "fl-float", false), TX("nk", "2")]);
  rise(["box1", "mountain1"], ig + 0.1, 0, 0.9);
  tl.fromTo("#lab-ign", { opacity: 0, z: 20 }, { opacity: 1, z: 90, duration: 0.7, ease: "expo.out", immediateRender: false }, ig + 0.4);
  tl.to("#pc", { opacity: 0, duration: 0.3 }, o + 42.4);
  tl.to("#lab-ign", { opacity: 0, duration: 0.4 }, o + 42.6);

  /* KEEP */
  at(o + 43, [["scn", 5]]); CHAPTERS.push([o + 42.8, "kKeep"]); hit(o + 43, "bar");
  mv("#card", { ...K.away, rotationY: -60 }, o + 43, 1.8); mv("#board", B.keep, o + 43, 2.1);
  rise(["smooth1", "color1"], o + 43.2, 0, 1.2, 0);
  cap(o + 43.8, "kKeep", "s12", { x: 64, y: 92 });
  [["OUT_geo", 44.4], ["merge1", 44.75], ["transform1", 45.1], ["file_tree", 45.1], ["file_rock", 45.45], ["ctrl", 46.2]].map(([n, t]) => [n, t + o]).forEach(([n, t], i) => { at(t, ND([n], "kept")); rise([n], t, 30, 0.7); sfx(t, "blip" + i, 0.4); });
  tl.fromTo("#side div", { opacity: 0, y: 22 }, { opacity: 1, y: 0, duration: 0.6, ease: "expo.out", stagger: 0.3, immediateRender: false }, o + 44.5);
  tl.to("#side div", { opacity: 0, y: -10, duration: 0.45, stagger: 0.05 }, o + 49.4);

  /* INSTALL */
  at(o + 49.8, [["scn", 6]]); hit(o + 49.8, "bar");
  tl.to("#capb", { opacity: 0, duration: 0.4 }, o + 49.6);
  mv("#board", B.gone, o + 49.7, 2.2, "power3.in");
  tl.to("#veil", { opacity: 0.55, duration: 1.6, ease: "power2.inOut" }, o + 50.2);
  tl.to("#logo", { x: 0, y: -40, scale: 1, duration: 1.6, ease: SM }, o + 50.4); sfx(o + 51.2, "shimmer", 0.45);
  tl.fromTo("#facts div", { opacity: 0, y: 22 }, { opacity: 1, y: 0, duration: 0.8, ease: "expo.out", stagger: 0.12, immediateRender: false }, o + 51.4);
  const END = Math.max(TOTAL, o + 57);
  tl.set({}, {}, END);
  D.sort((a, b) => a[0] - b[0]);

  /* ---------- frame sampling ---------- */
  const flush = () => void stage.offsetWidth;
  const transitions = () => root.getAnimations({ subtree: true }).filter((a) => typeof CSSTransition !== "undefined" && a instanceof CSSTransition);
  function frame(t) {
    tl.seek(t, false);
    transitions().forEach((a) => a.cancel());
    // settle every class/text change older than the transition window, with transitions off
    stage.classList.add("nt");
    for (const [k, v] of stateAt(t - TRANSITION_WINDOW)) applyKey(k, v);
    flush();
    stage.classList.remove("nt");
    flush();
    // replay recent changes with transitions on, then pin each transition at its exact age
    for (const [tt, p] of D) {
      if (tt <= t - TRANSITION_WINDOW) continue;
      if (tt > t) break;
      for (const [k, v] of p) applyKey(k, v);
      for (const a of transitions()) if (a.__age === undefined) { a.__age = t - tt; a.pause(); a.currentTime = a.__age * 1000; }
    }
  }
  return { frame, end: END, chapters: CHAPTERS, anchors: ANCHORS, sfx: SFX.sort((a, b) => a[0] - b[0]), destroy: () => { tl.kill(); } };
}
