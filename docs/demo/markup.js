// Stage markup for the hipcheck film. Text marked data-i18n is filled in timeline.js.
export const MARKUP = `
<div class="stage" id="stage">
  <div class="glow" id="g1"></div><div class="glow" id="g2"></div>
  <div class="world"><div id="rig">
    <div id="board">
      <div class="crumb"><span><b></b>obj</span><span>geo1</span></div>
      <svg id="wires" viewBox="0 0 720 420"></svg>
      <div id="nodes" style="position:absolute;inset:0;transform-style:preserve-3d"></div>
      <div class="blab" id="lab-float" data-i18n="lf"></div>
      <div class="blab" id="lab-unused" data-i18n="lu"></div>
      <div class="blab" id="lab-ign" data-i18n="li"></div>
    </div>
    <div id="dock"><i class="ic"></i><i class="ic"></i><i class="ic"></i><div id="dock-hc"><b></b>hipcheck</div><div class="ptr" id="pd"></div></div>
    <div id="card">
      <div class="chd"><b></b>hipcheck<span class="pill" id="b-rescan">Rescan</span></div>
      <div class="segc"><i id="thumb"></i><div class="on" id="tab-check">Check <em id="nc">3</em></div><div id="tab-clean">Clean <em id="nk">4</em></div></div>
      <div class="pages">
        <div class="pg" id="pg-check">
          <div class="row" id="c0"><i class="d" style="background:var(--missing)"></i><span class="k">Missing file</span><span class="p">file_tree · $HIP/geo/tree_v03.bgeo</span></div>
          <div class="row" id="c1"><i class="d" style="background:var(--abs)"></i><span class="k">Absolute path</span><span class="p">file_rock · D:/assets/rock.bgeo</span></div>
          <div class="row" id="c2"><i class="d" style="background:var(--abs)"></i><span class="k">Absolute path</span><span class="p">bark/diffuse · //server/tex/bark.exr</span></div>
        </div>
        <div class="pg" id="pg-clean">
          <div class="row grp" id="k-float"><i class="d" style="background:var(--float)"></i><span class="k">Floating · 2</span></div>
          <div class="row" id="k-box1"><span class="k">box1</span><span class="ty">Box</span><span class="jmp"></span></div>
          <div class="row" id="k-mountain1"><span class="k">mountain1</span><span class="ty">Mountain</span><span class="jmp"></span></div>
          <div class="row grp" id="k-unused"><i class="d" style="background:var(--unused)"></i><span class="k">Unused branch · 2</span></div>
          <div class="row" id="k-smooth1"><span class="k">smooth1</span><span class="ty">Smooth</span><span class="jmp"></span></div>
          <div class="row" id="k-color1"><span class="k">color1</span><span class="ty">Color</span><span class="jmp"></span></div>
          <div class="empty" id="k-empty">No unused nodes in /obj/geo1</div>
        </div>
      </div>
      <div class="cft"><span class="pill" id="b-sa">Select All</span><span class="pill" id="b-color">Color Selected</span><span class="pill" id="b-ign">Ignore Selected</span><span class="pill" id="b-del">Delete Selected</span></div>
      <div class="sheet" id="sheet"><p>Delete 4 unused nodes?</p><div class="acts"><span class="pill">Cancel</span><span class="pill" id="s-ok">Delete</span></div></div>
      <div class="ptr" id="pc"></div>
    </div>
    <div id="keys"><div class="key" id="key-c">Ctrl</div><div class="key z" id="key-z">Z</div></div>
  </div></div>

  <div class="nf" id="nf"><span class="t" data-i18n="nf"></span><span class="pill" data-i18n="nf1"></span><span class="pill" data-i18n="nf2"></span><span class="pill" data-i18n="nf3"></span></div>
  <div class="side" id="side"><div data-i18n="k1"></div><div data-i18n="k2"></div><div data-i18n="k3"></div><div data-i18n="k4"></div><div data-i18n="k5"></div></div>

  <div class="veil" id="veil"></div>
  <div class="wheel" id="wheel"><div class="drum" id="drum"></div></div></div>
  <div class="logo" id="logo"></div>
  <div class="tagl" id="tag1" data-i18n="t1"></div>
  <div class="facts" id="facts">
    <div><b>Houdini 21</b><span data-i18n="o1"></span></div>
    <div><b data-i18n="o2h"></b><span data-i18n="o2"></span></div>
    <div><b>Ctrl+Z</b><span data-i18n="o3"></span></div>
    <div><b>21 / 21</b><span data-i18n="o4"></span></div>
  </div>
  <div id="capw"><div id="capb"><div id="ck"></div><div id="cs"></div></div></div>
  <div class="scn" id="scn"></div>
</div>`;
