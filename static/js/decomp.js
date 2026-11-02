// Interactive figures for the DecompRCA project page.
// All numbers are copied from the camera-ready paper (Tables 2-4) and
// method/results/retrieval_saturation.csv (appendix saturation figure).
(function () {
  'use strict';

  function segToggle(a, b, fn) {
    a.addEventListener('click', function () { a.setAttribute('aria-pressed', 'true'); b.setAttribute('aria-pressed', 'false'); fn(false); });
    b.addEventListener('click', function () { b.setAttribute('aria-pressed', 'true'); a.setAttribute('aria-pressed', 'false'); fn(true); });
  }
  function pct(x) { return Math.round(x * 100); }
  function f3(v) { return v.toFixed(3).replace(/^0/, ''); }

  // ---------------- Failure ledger (Tables 2 and 3) ----------------
  // ret = Retrieval@15 of the multi-signal retriever; noDK / dk = LLM top@1 (mean of 3 runs);
  // baro = BARO top@1 (best statistical baseline).
  var LEDGER = [
    { g: 'Industrial control systems' },
    { name: 'WADI', n: 14, sys: 'water distribution', ret: 0.64, noDK: 0.333, dk: 0.310, baro: 0.214 },
    { name: 'SWaT', n: 36, sys: 'water treatment', ret: 0.67, noDK: 0.213, dk: 0.148, baro: 0.194 },
    { name: 'HVAC', n: 48, sys: 'building management', ret: 0.63, noDK: 0.153, dk: 0.278, baro: 0.000 },
    { g: 'Microservices (RCAEval)' },
    { name: 'Online Boutique', n: 125, sys: 'RE1-OB', ret: 0.98, noDK: 0.875, dk: 0.888, baro: 0.784 },
    { name: 'Sock Shop', n: 125, sys: 'RE1-SS', ret: 1.00, noDK: 0.872, dk: 0.944, baro: 0.856 },
    { name: 'Train Ticket', n: 125, sys: 'RE1-TT', ret: 0.91, noDK: 0.653, dk: 0.685, baro: 0.560 }
  ];
  var ledger = document.getElementById('ledger');
  var bars = [];
  LEDGER.forEach(function (d) {
    if (d.g) {
      var h = document.createElement('div'); h.className = 'group'; h.textContent = d.g; ledger.appendChild(h); return;
    }
    var row = document.createElement('div'); row.className = 'row';
    row.innerHTML = '<div class="name">' + d.name + '<span>' + d.sys + ' · n=' + d.n + '</span></div>' +
      '<div class="bar" role="img"><i class="hit"></i><i class="rr"></i><i class="rt"></i>' +
      '<span class="baro" title="BARO top@1 ' + d.baro.toFixed(3) + '"></span></div>';
    ledger.appendChild(row);
    bars.push({ d: d, el: row.querySelector('.bar') });
  });
  function drawLedger(useDK) {
    bars.forEach(function (b) {
      var d = b.d, hit = useDK ? d.dk : d.noDK, rr = Math.max(0, d.ret - hit), rt = 1 - d.ret;
      var s = b.el.children;
      [[s[0], hit], [s[1], rr], [s[2], rt]].forEach(function (p) {
        p[0].style.flex = '0 0 ' + (p[1] * 100) + '%';
        p[0].textContent = p[1] >= 0.09 ? pct(p[1]) + '%' : '';
      });
      s[3].style.left = (d.baro * 100) + '%';
      b.el.setAttribute('aria-label', d.name + ': correct ' + pct(hit) + '%, reranking failure ' + pct(rr) +
        '%, retrieval failure ' + pct(rt) + '%, BARO top@1 ' + pct(d.baro) + '%');
    });
  }
  segToggle(document.getElementById('dk-off'), document.getElementById('dk-on'), drawLedger);
  drawLedger(false);

  // ---------------- Saturation explorer ----------------
  var SAT = {"WADI":{"K":[1,2,3,5,7,10,15,20,25,30,40,50],"mag":[0.286,0.286,0.357,0.357,0.357,0.429,0.643,0.714,0.714,0.786,0.857,0.929],"ons":[0.071,0.071,0.214,0.429,0.5,0.5,0.714,0.714,0.857,0.857,0.857,0.857],"stc":[0.286,0.357,0.357,0.357,0.429,0.429,0.429,0.429,0.429,0.429,0.429,0.429]},"SWaT":{"K":[1,2,3,5,7,10,15,20,25,30,40,50],"mag":[0.167,0.194,0.222,0.333,0.333,0.444,0.528,0.611,0.667,0.75,0.861,0.889],"ons":[0.028,0.111,0.139,0.361,0.528,0.583,0.667,0.806,0.806,0.889,0.889,0.889],"stc":[0.111,0.361,0.361,0.361,0.417,0.417,0.417,0.417,0.417,0.417,0.417,0.417]},"HVAC":{"K":[1,2,3,5,7,10,15,20,25,30,40,50],"mag":[0.0,0.021,0.021,0.208,0.25,0.271,0.354,0.375,0.417,0.438,0.479,0.604],"ons":[0.021,0.042,0.354,0.479,0.521,0.667,0.667,0.667,0.667,0.708,0.771,0.812],"stc":[0.25,0.25,0.25,0.25,0.25,0.25,0.25,0.25,0.25,0.25,0.25,0.25]},"RE1-OB":{"K":[1,2,3,5,7,10,15,20,25,30,40,50],"mag":[0.784,0.904,0.936,0.976,0.992,1.0,1.0,1.0,1.0,1.0,1.0,1.0],"ons":[0.112,0.184,0.28,0.368,0.52,0.736,0.888,0.96,0.984,1.0,1.0,1.0],"stc":[0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]},"RE1-SS":{"K":[1,2,3,5,7,10,15,20,25,30,40,50],"mag":[0.856,0.952,0.992,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0],"ons":[0.168,0.24,0.32,0.584,0.672,0.8,0.88,0.968,1.0,1.0,1.0,1.0],"stc":[0.12,0.144,0.152,0.152,0.152,0.152,0.152,0.152,0.152,0.152,0.152,0.152]},"RE1-TT":{"K":[1,2,3,5,7,10,15,20,25,30,40,50],"mag":[0.56,0.736,0.832,0.912,0.968,0.976,0.984,0.992,0.992,0.992,0.992,0.992],"ons":[0.0,0.016,0.04,0.048,0.072,0.088,0.16,0.2,0.272,0.392,0.512,0.68],"stc":[0.0,0.016,0.024,0.04,0.04,0.04,0.04,0.04,0.04,0.04,0.04,0.04]}};
  var DIRECT = 'The cause is usually the metric with the largest deviation, so magnitude alone retrieves it and the other signals add little.';
  var REGIME = {
    'WADI': ['Lag-dominated', 'Downstream effects rank above the cause at small K, and magnitude only catches up with a larger budget. Onset gets there with a smaller K.'],
    'SWaT': ['Lag-dominated', 'Actuator faults are abrupt, so state change gives the biggest gain at small K, and onset passes magnitude from K=5.'],
    'HVAC': ['Amplitude-suppressed', 'Setpoint drifts are gradual and barely register in magnitude (0.60 even at K=50), while onset reaches 0.67 by K=10.'],
    'RE1-OB': ['Direct fault', DIRECT], 'RE1-SS': ['Direct fault', DIRECT], 'RE1-TT': ['Direct fault', DIRECT]
  };
  var SIG = [['mag', 'magnitude', '--sig-mag', ''], ['ons', 'onset', '--sig-ons', '6 4'], ['stc', 'state change', '--sig-stc', '2 3']];
  var cur = 'HVAC', kIdx = 6;
  var W = 640, H = 300, ml = 40, mr = 14, mt = 12, mb = 36;
  function x(k) { return ml + (k / 50) * (W - ml - mr); }
  function y(v) { return mt + (1 - v) * (H - mt - mb); }
  var NS = 'http://www.w3.org/2000/svg';
  function el(t, a, p) { var e = document.createElementNS(NS, t); for (var k in a) e.setAttribute(k, a[k]); if (p) p.appendChild(e); return e; }

  var tabs = document.getElementById('sat-tabs');
  Object.keys(SAT).forEach(function (name) {
    var b = document.createElement('button');
    b.type = 'button'; b.textContent = name; b.setAttribute('aria-pressed', name === cur ? 'true' : 'false');
    b.addEventListener('click', function () {
      cur = name;
      Array.prototype.forEach.call(tabs.children, function (c) { c.setAttribute('aria-pressed', c === b ? 'true' : 'false'); });
      drawSat();
    });
    tabs.appendChild(b);
  });
  var slider = document.getElementById('sat-k');
  slider.addEventListener('input', function () { kIdx = +slider.value; drawSat(); });

  function drawSat() {
    var d = SAT[cur], host = document.getElementById('sat-chart'); host.innerHTML = '';
    var svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': 'Retrieval at K versus K for ' + cur });
    var g = el('g', { 'class': 'grid' }, svg), ax = el('g', { 'class': 'axis' }, svg);
    [0, 0.25, 0.5, 0.75, 1].forEach(function (v) {
      el('line', { x1: ml, x2: W - mr, y1: y(v), y2: y(v) }, g);
      el('text', { x: ml - 8, y: y(v) + 4, 'text-anchor': 'end' }, ax).textContent = v.toFixed(2).replace(/^0/, '');
    });
    [1, 10, 20, 30, 40, 50].forEach(function (k) {
      el('text', { x: x(k), y: H - mb + 18, 'text-anchor': 'middle' }, ax).textContent = k;
    });
    el('text', { x: W - mr, y: H - 2, 'text-anchor': 'end', 'class': 'title' }, ax).textContent = 'CANDIDATE BUDGET K';
    el('line', { x1: x(15), x2: x(15), y1: mt, y2: H - mb, 'class': 'k15' }, svg);
    el('text', { x: x(15) + 4, y: mt + 10, 'class': 'k15-label' }, svg).textContent = 'K=15';
    var kk = d.K[kIdx];
    el('line', { x1: x(kk), x2: x(kk), y1: mt, y2: H - mb, 'class': 'guide' }, svg);
    SIG.forEach(function (s) {
      var pts = d.K.map(function (k, i) { return x(k) + ',' + y(d[s[0]][i]); }).join(' ');
      el('polyline', { points: pts, 'class': 'line', style: 'stroke:var(' + s[2] + ')', 'stroke-dasharray': s[3] }, svg);
      el('circle', { cx: x(kk), cy: y(d[s[0]][kIdx]), r: 4.5, style: 'fill:var(' + s[2] + ');stroke:#fff;stroke-width:2' }, svg);
    });
    host.appendChild(svg);
    document.getElementById('sat-kval').textContent = kk;
    document.getElementById('sat-regime').innerHTML = '<strong>' + REGIME[cur][0] + '</strong>' + REGIME[cur][1];
    document.getElementById('sat-vals').innerHTML = SIG.map(function (s, i) {
      return '<span><i style="border-color:var(' + s[2] + ');border-top-style:' + ['solid', 'dashed', 'dotted'][i] + '"></i>' +
        s[1] + ' ' + d[s[0]][kIdx].toFixed(2) + '</span>';
    }).join('');
  }
  drawSat();

  // ---------------- Results tables (Tables 3 and 4) ----------------
  var COLS = ['WADI', 'SWaT', 'HVAC', 'RE1-OB', 'RE1-SS', 'RE1-TT'];
  // [label, values, std (optional), isOurs, isDelta]
  var E2E = [
    { sub: 'Statistical' },
    ['BARO', [.214, .194, .000, .784, .856, .560]],
    ['RCD', [.071, .083, .083, .304, .248, .144]],
    ['ε-Diagnosis', [.000, .028, .146, .072, .232, .008]],
    { sub: 'Graph-based' },
    ['CIRCA (PC)', [.214, .083, .062, .536, .632, .320]],
    ['CIRCA (FCI)', [.214, .111, .104, .576, .624, .328]],
    ['PageRank (PC)', [.000, .028, .021, .112, .136, .008]],
    ['PageRank (FCI)', [.071, .000, .000, .096, .184, .048]],
    ['RandomWalk (PC)', [.071, .000, .000, .080, .112, .064]],
    ['RandomWalk (FCI)', [.000, .000, .000, .112, .144, .072]],
    { sub: 'Ours: multi-signal retriever + LLM reranker' },
    ['LLM (no DK)', [.333, .213, .153, .875, .872, .653], [.082, .016, .043, .009, .024, .024], 1],
    ['LLM (with DK)', [.310, .148, .278, .888, .944, .685], [.041, .016, .012, .008, .008, .009], 1]
  ];
  var CTL = [
    { sub: 'Best of nine baselines on the same pool' },
    ['Best baseline', [.308, .200, .188, .784, .856, .560]],
    { sub: 'Ours' },
    ['LLM (no DK)', [.410, .229, .188, .883, .859, .688], [.044, .029, .055, .005, .009, .024], 1],
    ['LLM (with DK)', [.436, .267, .326, .891, .928, .741], [.089, .017, .012, .012, .000, .009], 1],
    { sub: 'Lead over best baseline (points)' },
    ['Δ', [12.8, 6.7, 13.9, 10.7, 7.2, 18.1], null, 0, 1]
  ];
  var CAP = {
    e2e: 'End-to-end top@1. LLM rows show mean ± std over 3 runs at temperature 1.0; other rows are single runs. For HVAC, causes the retriever misses count as misses in the LLM rows. The best value in each column is underlined.',
    ctl: 'Retriever pool (K=15) with the true cause added to every pool, and all nine baselines re-run on the same candidates. WADI and SWaT have n=13 and n=35 because causes outside the evaluated sensor set cannot be added. The best value in each column is underlined.'
  };
  var tbl = document.getElementById('results-table');
  function drawTable(ctl) {
    var rows = ctl ? CTL : E2E;
    var best = COLS.map(function (_, c) {
      var m = -1; rows.forEach(function (r) { if (r[1] && !r[4]) m = Math.max(m, r[1][c]); }); return m;
    });
    var h = '<thead><tr class="span"><th></th><th colspan="3">Industrial control systems</th>' +
      '<th colspan="3" class="sep">Microservices (RCAEval)</th></tr><tr><th>Method</th>' +
      COLS.map(function (c, i) { return '<th' + (i === 3 ? ' class="sep"' : '') + '>' + c + '</th>'; }).join('') + '</tr></thead><tbody>';
    rows.forEach(function (r) {
      if (r.sub) { h += '<tr class="sub"><td colspan="7">' + r.sub + '</td></tr>'; return; }
      h += '<tr' + (r[3] ? ' class="ours"' : '') + '><td>' + r[0] + '</td>' + r[1].map(function (v, c) {
        var cls = c === 3 ? ['sep'] : [];
        if (r[4]) return '<td class="' + cls.join(' ') + '">+' + v.toFixed(1) + '</td>';
        if (Math.abs(v - best[c]) < 1e-9) cls.push('best');
        return '<td class="' + cls.join(' ') + '">' + f3(v) + (r[2] ? '<span class="sd">±' + f3(r[2][c]) + '</span>' : '') + '</td>';
      }).join('') + '</tr>';
    });
    tbl.innerHTML = h + '</tbody>';
    document.getElementById('results-caption').textContent = ctl ? CAP.ctl : CAP.e2e;
  }
  segToggle(document.getElementById('t-e2e'), document.getElementById('t-ctl'), drawTable);
  drawTable(false);
})();
