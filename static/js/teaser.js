// Animated teaser (illustrative example, not a dataset case).
//
// Part 1: the same fault in a direct (microservice-style) and a propagating
// (industrial-CPS-style) system, ranked by deviation magnitude. Direct: the
// cause comes first. Propagating: it is buried under its own effects.
//
// Part 2: zoom in on the propagating fault with two cases side by side, each
// with a two-check scorecard (1 Retrieval, 2 Reranking).
//   A: magnitude-only retriever. The cause never enters the pool:
//      retrieval failure, reranking never reached.
//   B: retriever adds onset. The cause enters the pool, but reranking by
//      loudness drops it to 4th: reranking failure.
(function () {
  'use strict';

  var W = 500, H = 400;
  var COLX = [45, 110, 175, 240], ROWY = [150, 220, 290];
  var LISTX = 322, ROWS = [150, 200, 250, 300], RESULT_Y = 352;
  var CAUSE = 'n00';
  var EDGES = [['n00', 'n10'], ['n00', 'n11'], ['n01', 'n11'], ['n02', 'n12'],
    ['n10', 'n20'], ['n11', 'n21'], ['n12', 'n22'],
    ['n20', 'n30'], ['n21', 'n30'], ['n21', 'n31'], ['n22', 'n32']];
  var LABELS = {
    services: [['payment', 'auth', 'catalog'], ['checkout', 'orders', 'search'], ['cart', 'gateway', 'recs'], ['frontend', 'web', 'ads']],
    plant: [['MV101', 'P101', 'AIT101'], ['LIT201', 'FIT201', 'AIT201'], ['LIT301', 'P301', 'DPIT301'], ['LIT401', 'FIT401', 'P401']]
  };
  var DEV = {
    // strongest at the origin, fading as it spreads
    direct: { n00: 1.0, n10: 0.55, n11: 0.45, n20: 0.32, n21: 0.28, n30: 0.18, n31: 0.14 },
    // quiet at the origin, amplified downstream
    prop: { n00: 0.2, n10: 0.4, n11: 0.45, n20: 0.68, n21: 0.62, n30: 1.0, n31: 0.9 }
  };
  // Part 1 scenes
  var DIRECT = { tag: 'Direct fault · like microservices', tagCls: 'direct', labels: 'services', dev: 'direct', pool: ['n00', 'n10', 'n11', 'n20'] };
  var PROP = { tag: 'Propagating fault · like industrial control systems', tagCls: 'prop', labels: 'plant', dev: 'prop', pool: ['n30', 'n31', 'n20', 'n21'] };
  // Part 2 cases (pool = arrival order during retrieval, rank = order after reranking by loudness)
  var CASE_A = { tag: 'A · Retriever: magnitude only', tagCls: 'neutral', endTag: 'A · Retrieval failure', endCls: 'retr',
    labels: 'plant', dev: 'prop', pool: ['n30', 'n31', 'n20', 'n21'], rank: ['n30', 'n31', 'n20', 'n21'],
    ret: false, end: { text: 'top@1 = 0 × n/a = 0', cls: 'miss' } };
  var CASE_B = { tag: 'B · Retriever: magnitude + onset', tagCls: 'neutral', endTag: 'B · Reranking failure', endCls: 'rerank',
    labels: 'plant', dev: 'prop', pool: ['n00', 'n30', 'n31', 'n20'], rank: ['n30', 'n31', 'n20', 'n00'],
    ret: true, end: { text: 'top@1 = 1 × 0 = 0', cls: 'rerank' } };

  // Timeline (ms from start)
  var T = { start: 400, cols: [3200, 4300, 5400], list: 7800, pick0: 8100, pickStep: 500, result: 11800,
    zoom: 16000, retr: 19500, retrPick0: 19900, retrPickStep: 550, retrCheck: 23000,
    rerank: 25000, rerankMove: 25500, rerankCheck: 27300, takeaway: 29500, next: 38500 };
  // Stretch the whole timeline (viewers can click to skip ahead).
  var SLOW = 1.45;
  Object.keys(T).forEach(function (k) {
    T[k] = Array.isArray(T[k]) ? T[k].map(function (v) { return Math.round(v * SLOW); }) : Math.round(T[k] * SLOW);
  });

  // Narration text may contain <mark> highlights: plain = key idea, .ok = what works,
  // .retr = retrieval (red), .rr = reranking (amber).
  var NARR = [
    [T.start, 'Step 1 · Fault starts', 'step', 'The <mark>same fault</mark> starts at one component in two different systems.'],
    [T.cols[0], 'Step 2 · Fault spreads', 'step', 'On the left, the fault <mark>weakens</mark> as it spreads. On the right, its downstream effects end up <mark>larger than the deviation at the cause</mark>.'],
    [T.list, 'Step 3 · Rank by magnitude', 'step', 'Both systems are analysed the same way: rank all sensors by <mark>how far they deviate</mark> and keep the top 4.'],
    [T.result, 'Result', 'hit', 'The results differ. Magnitude <mark class="ok">finds the cause of the direct fault</mark>, but the cause of the propagating fault <mark class="retr">ends up below its own effects</mark>.'],
    [T.zoom, 'Two ways to fail', 'step', 'Now take the propagating fault. An RCA method first <mark class="retr">retrieves</mark> a pool of candidates and then <mark class="rr">ranks</mark> it. Cases A and B use different retrievers.'],
    [T.retr, 'Stage 1 · Retrieval', 'retr', '<mark class="retr">Is the true cause in the pool?</mark> A uses magnitude only and <mark class="retr">misses the quiet cause</mark>. B also uses onset and <mark class="ok">picks it up</mark>.'],
    [T.rerank, 'Stage 2 · Reranking', 'rerank', '<mark class="rr">Is it ranked first?</mark> B sorts its pool by magnitude, and the cause <mark class="rr">drops to 4th</mark>. A never reaches this step because the cause is not in its pool.'],
    [T.takeaway, 'Takeaway', 'hit', 'Both cases end at <mark>top@1 = 0</mark>, but A failed at <mark class="retr">retrieval</mark> and B at <mark class="rr">reranking</mark>. They need different fixes, and top@k alone does not say which.',
      '<span class="u-out">top@k</span> = <span class="u-ret">Retrieval@K</span> × <span class="u-rr">Rerank@k</span>']
  ];

  // ---------- helpers ----------
  var NS = 'http://www.w3.org/2000/svg';
  function svgEl(t, a, p) { var e = document.createElementNS(NS, t); for (var k in a) e.setAttribute(k, a[k]); if (p) p.appendChild(e); return e; }
  function place(el, x, y) { el.style.left = (x / W * 100) + '%'; el.style.top = (y / H * 100) + '%'; }
  function nodeXY(id) { return [COLX[+id[1]], ROWY[+id[2]]]; }
  function eachNode(fn) { for (var c = 0; c < 4; c++) for (var r = 0; r < 3; r++) fn('n' + c + r, c, r); }
  function lerp(a, b, t) { return Math.round(a + (b - a) * t); }
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  var root = document.querySelector('.demo[data-demo="regime"]');
  if (!root) return;
  var grid = root.querySelector('.fp-grid');
  grid.setAttribute('role', 'button');
  grid.setAttribute('tabindex', '0');
  grid.setAttribute('aria-label', 'Animation in two parts. First, the same fault in a direct and a propagating system: ranking by deviation magnitude puts the direct fault\'s cause first but buries the propagating fault\'s cause under its effects. Second, two cases of the propagating fault. In case A the retriever uses magnitude only and the cause never enters the candidate pool, a retrieval failure. In case B the retriever adds onset, so the cause enters the pool, but reranking by loudness drops it to fourth, a reranking failure. Activate to skip to the next step.');

  function buildPanel(el) {
    var P = { el: el, edges: {}, tokens: {}, rankNums: [] };
    P.tag = document.createElement('span');
    el.appendChild(P.tag);
    var svg = svgEl('svg', { viewBox: '0 0 ' + W + ' ' + H, 'aria-hidden': 'true', 'class': 'fp-svg' });
    el.appendChild(svg);
    EDGES.forEach(function (e) {
      var a = nodeXY(e[0]), b = nodeXY(e[1]);
      P.edges[e[0] + e[1]] = svgEl('line', { x1: a[0], y1: a[1], x2: b[0], y2: b[1], 'class': 'edge' }, svg);
    });
    eachNode(function (id) {
      var p = nodeXY(id);
      var g = svgEl('circle', { cx: p[0], cy: p[1], r: 9, 'class': 'ghost' }, svg);
      if (id === CAUSE) P.causeGhost = g;
    });
    var cp = nodeXY(CAUSE);
    P.causeTag = svgEl('text', { x: cp[0] - 16, y: cp[1] - 26, 'class': 'cause-tag' }, svg);
    P.listTitle = svgEl('text', { x: LISTX - 22, y: ROWS[0] - 34, 'class': 'zone-title' }, svg);
    ROWS.forEach(function (y, i) {
      svgEl('rect', { x: LISTX - 22, y: y - 21, width: 175, height: 42, rx: 8, 'class': 'slot' }, svg);
      var n = svgEl('text', { x: LISTX - 30, y: y + 5, 'text-anchor': 'end', 'class': 'rank-num' }, svg);
      n.textContent = i + 1;
      P.rankNums.push(n);
    });
    eachNode(function (id) {
      var t = document.createElement('div');
      t.innerHTML = '<span class="tk-dot"></span><span class="tk-lab"></span>';
      el.appendChild(t);
      P.tokens[id] = t;
    });
    P.result = document.createElement('div');
    el.appendChild(P.result);
    place(P.result, LISTX - 22, RESULT_Y);
    P.card = document.createElement('div');
    P.card.className = 'scorecard';
    P.card.innerHTML = '<span class="sc" data-k="ret"><i>1</i>Retrieval<b></b></span><span class="sc" data-k="rr"><i>2</i>Reranking<b></b></span>';
    el.appendChild(P.card);
    place(P.card, 30, 360);
    P.sc = { ret: P.card.querySelector('[data-k="ret"]'), rr: P.card.querySelector('[data-k="rr"]') };
    return P;
  }
  var panelEls = grid.querySelectorAll('.fp');
  var left = buildPanel(panelEls[0]);
  var right = buildPanel(panelEls[1]);
  var panels = [left, right];

  var narr = root.querySelector('.teaser-narration');
  var narrStep = narr.querySelector('.narr-step');
  var narrText = narr.querySelector('.narr-text');
  var narrEq = narr.querySelector('.narr-eq');
  var playBtn = root.querySelector('.play-btn');
  var replayBtn = root.querySelector('.replay-btn');

  // ---------- state helpers ----------
  function setDev(P, id, d) {
    var dot = P.tokens[id].querySelector('.tk-dot');
    dot.style.transform = 'scale(' + (1 + d * 0.95) + ')';
    // light slate -> template primary blue as the deviation grows
    dot.style.background = d > 0 ? 'rgb(' + lerp(203, 37, d) + ',' + lerp(213, 99, d) + ',' + lerp(225, 235, d) + ')' : '';
  }
  function narrate(n) {
    narrStep.textContent = n[1];
    narr.dataset.tone = n[2];
    narrText.innerHTML = n[3];
    narrEq.innerHTML = n[4] || '';
    narrEq.hidden = !n[4];
    narr.classList.remove('in'); void narr.offsetWidth; narr.classList.add('in');
  }
  function setTag(P, text, cls) { P.tag.textContent = text; P.tag.className = 'fp-tag ' + cls; }
  function pick(P, id, row) {
    var t = P.tokens[id];
    t.classList.remove('in-plant');
    t.classList.add('picked');
    place(t, LISTX, ROWS[row]);
  }
  function result(P, text, cls) { P.result.textContent = text; P.result.className = 'fp-result show ' + cls; }
  function missed(P, on, text) {
    P.causeGhost.classList.toggle('missed', on);
    P.causeGhost.setAttribute('r', on ? 17 : 9);
    P.causeTag.classList.toggle('missed', on);
    P.causeTag.textContent = text;
  }
  function check(P, k, state) {
    var marks = { pending: '…', pass: '✓', fail: '✗', na: 'not reached' };
    P.sc[k].className = 'sc ' + state + (k === 'rr' && state === 'fail' ? ' amber' : '');
    P.sc[k].querySelector('b').textContent = marks[state];
  }
  function showNums(P, on) { P.rankNums.forEach(function (n) { n.style.opacity = on ? 1 : 0; }); }

  // Put a panel into a fresh scene: labels, tag, all tokens back in the plant.
  // spread=true applies the scene's full deviation pattern at once (Part 2).
  function scene(P, cfg, spread) {
    P.cfg = cfg;
    P.dev = DEV[cfg.dev];
    setTag(P, cfg.tag, cfg.tagCls);
    eachNode(function (id, c, r) {
      var t = P.tokens[id], p = nodeXY(id);
      place(t, p[0], p[1]);
      t.className = 'tk in-plant' + (id === CAUSE ? ' is-cause' : '');
      t.querySelector('.tk-lab').textContent = LABELS[cfg.labels][c][r];
      setDev(P, id, spread && P.dev[id] ? P.dev[id] : 0);
    });
    EDGES.forEach(function (e) {
      P.edges[e[0] + e[1]].classList.toggle('hot', !!(spread && P.dev[e[0]] && P.dev[e[1]]));
    });
    missed(P, false, 'true cause');
    P.listTitle.textContent = spread ? 'Candidate pool (K=4)' : 'Top 4 by magnitude';
    showNums(P, !spread);
    P.result.className = 'fp-result';
    P.result.textContent = '';
    P.card.classList.toggle('show', !!spread);
    if (spread) { check(P, 'ret', 'pending'); check(P, 'rr', 'pending'); }
    P.el.classList.remove('fade');
  }

  function reset() {
    grid.classList.add('no-anim');
    scene(left, DIRECT, false);
    scene(right, PROP, false);
    void grid.offsetWidth;
    grid.classList.remove('no-anim');
  }

  function steps() {
    var L = [];
    NARR.forEach(function (n) { L.push([n[0], function () { narrate(n); }]); });

    // ---- Part 1: fault starts, spreads, gets ranked by magnitude ----
    L.push([T.start, function () {
      panels.forEach(function (P) { setDev(P, CAUSE, P.dev[CAUSE]); P.tokens[CAUSE].classList.add('pulse'); });
    }]);
    T.cols.forEach(function (t, k) {
      var col = k + 1;
      L.push([t, function () {
        panels.forEach(function (P) {
          EDGES.forEach(function (e) {
            if (+e[1][1] === col && P.dev[e[0]] && P.dev[e[1]]) P.edges[e[0] + e[1]].classList.add('hot');
          });
          Object.keys(P.dev).forEach(function (id) { if (+id[1] === col) setDev(P, id, P.dev[id]); });
        });
      }]);
    });
    L.push([T.list, function () { panels.forEach(function (P) { P.tokens[CAUSE].classList.remove('pulse'); }); }]);
    ROWS.forEach(function (_, i) {
      L.push([T.pick0 + i * T.pickStep, function () { panels.forEach(function (P) { pick(P, P.cfg.pool[i], i); }); }]);
    });
    L.push([T.result, function () {
      left.tokens[CAUSE].classList.add('ring-hit');
      result(left, 'True cause ranked 1st', 'ok');
      missed(right, true, 'true cause: 7th');
      result(right, 'True cause ranked 7th: missed', 'miss');
    }]);

    // ---- Part 2: two cases of the propagating fault ----
    L.push([T.zoom, function () { panels.forEach(function (P) { P.el.classList.add('fade'); }); }]);
    L.push([T.zoom + 700, function () {
      grid.classList.add('no-anim');
      scene(left, CASE_A, true);
      scene(right, CASE_B, true);
      panels.forEach(function (P) { P.el.classList.add('fade'); });
      void grid.offsetWidth;
      grid.classList.remove('no-anim');
      panels.forEach(function (P) { P.el.classList.remove('fade'); });
    }]);
    // Stage 1: retrieval fills each pool (unnumbered: a pool is a set)
    ROWS.forEach(function (_, i) {
      L.push([T.retrPick0 + i * T.retrPickStep, function () { panels.forEach(function (P) { pick(P, P.cfg.pool[i], i); }); }]);
    });
    L.push([T.retrCheck, function () {
      check(left, 'ret', 'fail');
      missed(left, true, 'never retrieved');
      check(right, 'ret', 'pass');
    }]);
    // Stage 2: reranking orders each pool by loudness
    L.push([T.rerank, function () {
      panels.forEach(function (P) { P.listTitle.textContent = 'Ranking'; showNums(P, true); });
    }]);
    L.push([T.rerankMove, function () {
      panels.forEach(function (P) { P.cfg.rank.forEach(function (id, i) { place(P.tokens[id], LISTX, ROWS[i]); }); });
    }]);
    L.push([T.rerankCheck, function () {
      check(left, 'rr', 'na');
      check(right, 'rr', 'fail');
      right.tokens[CAUSE].classList.add('ring-rerank');
    }]);
    L.push([T.takeaway, function () {
      panels.forEach(function (P) {
        setTag(P, P.cfg.endTag, P.cfg.endCls);
        result(P, P.cfg.end.text, P.cfg.end.cls);
      });
    }]);
    return L.sort(function (a, b) { return a[0] - b[0]; });
  }

  // ---------- playback ----------
  // Each run is a list of timed events. Playing: unfired events sit on timers.
  // Pause freezes everything in place: timers are cleared and every running
  // CSS transition/animation is paused via getAnimations(); resume picks up
  // from the same moment. Clicking the animation (or Next step) jumps to the
  // start of the next narration step, playing or paused.
  var BOUNDS = NARR.map(function (n) { return n[0]; });
  var nextBtn = root.querySelector('.next-btn');
  var events = [], timers = [], playing = !reduce, startedAt = 0, pausedAt = 0;
  function clear() { timers.forEach(clearTimeout); timers = []; }
  function anims() { return root.getAnimations ? root.getAnimations({ subtree: true }) : []; }
  // Freeze motion in place, but let a narration fade-in finish so the text stays readable.
  function freeze() {
    anims().forEach(function (a) { if (a.animationName === 'narr-in') a.finish(); else a.pause(); });
  }
  function markPlay() {
    playBtn.setAttribute('aria-label', playing ? 'Pause animation' : 'Play animation');
    playBtn.innerHTML = playing ? '<i class="fas fa-pause"></i>' : '<i class="fas fa-play"></i>';
  }
  function fire(ev) { if (!ev.done) { ev.done = true; ev.fn(); } }
  function runInstant(list) {
    grid.classList.add('no-anim');
    list.forEach(fire);
    void grid.offsetWidth;
    grid.classList.remove('no-anim');
  }
  // Fire the unfired events from time t onward on timers.
  function schedule(t) {
    clear();
    events.forEach(function (ev) {
      if (!ev.done) timers.push(setTimeout(function () { fire(ev); }, Math.max(0, ev.t - t)));
    });
    timers.push(setTimeout(function () { if (playing) jump(0, true); }, Math.max(0, T.next - t)));
    startedAt = Date.now() - t;
  }
  // Rebuild the state at time t: events before t (or up to t when `include`)
  // happen at once. Then either play on from t or stay paused there.
  function jump(t, play, include) {
    clear(); reset();
    events = steps().map(function (st) { return { t: st[0], fn: st[1], done: false }; });
    runInstant(events.filter(function (ev) { return include ? ev.t <= t : ev.t < t; }));
    playing = play;
    pausedAt = t;
    if (play) schedule(t);
    else freeze();
    markPlay();
  }
  function now() { return playing ? Date.now() - startedAt : pausedAt; }
  function pause() {
    pausedAt = now();
    clear();
    playing = false;
    freeze();
    markPlay();
  }
  function resume() {
    if (pausedAt >= T.next) { jump(0, true); return; }
    playing = true;
    anims().forEach(function (a) { if (a.playState === 'paused') a.play(); });
    schedule(pausedAt);
    markPlay();
  }
  function nextStep() {
    var t = now(), nb = null;
    for (var i = 0; i < BOUNDS.length; i++) if (BOUNDS[i] > t + 50) { nb = BOUNDS[i]; break; }
    if (nb === null) nb = playing ? 0 : BOUNDS[0];  // past the last step: start over
    if (playing) jump(nb, true);
    else jump(nb, false, true);  // paused: show the start of the next step, still paused
  }
  playBtn.addEventListener('click', function () { if (playing) pause(); else resume(); });
  replayBtn.addEventListener('click', function () { jump(0, true); });
  if (nextBtn) nextBtn.addEventListener('click', nextStep);
  grid.addEventListener('click', nextStep);
  grid.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowRight') { e.preventDefault(); nextStep(); }
  });

  // Reduced motion: open paused on the finished takeaway.
  if (playing) jump(0, true); else jump(T.next, false, true);
})();
