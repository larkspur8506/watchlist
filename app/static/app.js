/* 自选聚合页前端：拉 /api/quotes、渲染分组、5s 轮询（页面隐藏时暂停） */
(function () {
  "use strict";
  var $list = document.getElementById("list");
  var $stamp = document.getElementById("stamp");
  var $dot = document.getElementById("dot");
  var $note = document.getElementById("note");
  var $up = document.getElementById("up"), $down = document.getElementById("down"), $flat = document.getElementById("flat");
  var timer = null, lastSig = "";

  function fmtPrice(it) {
    if (it.price === null || it.price === undefined) return "—";
    var p = it.price;
    if (it.ccy === "GBX") return p.toFixed(1);
    return p < 100 ? p.toFixed(3) : p.toFixed(2);
  }
  function fmtChg(v) {
    if (v === null || v === undefined) return "—";
    return (v > 0 ? "+" : "") + v.toFixed(2) + "%";
  }
  function cls(v) {
    if (v === null || v === undefined) return "flat";
    return v > 0.0001 ? "up" : (v < -0.0001 ? "down" : "flat");
  }
  function sparkSVG(arr, dir) {
    var w = 48, h = 20;
    if (!arr || arr.length < 2) return "";
    var min = Math.min.apply(null, arr), max = Math.max.apply(null, arr);
    var span = max - min || 1;
    var pts = arr.map(function (v, i) {
      var x = (i / (arr.length - 1)) * (w - 2) + 1;
      var y = h - 2 - ((v - min) / span) * (h - 4);
      return x.toFixed(1) + "," + y.toFixed(1);
    }).join(" ");
    var color = dir === "up" ? "var(--up)" : (dir === "down" ? "var(--down)" : "var(--dim2)");
    return '<svg class="spark" viewBox="0 0 ' + w + " " + h + '" preserveAspectRatio="none">' +
           '<polyline fill="none" stroke="' + color + '" stroke-width="1.4" points="' + pts + '"/></svg>';
  }
  function hhmmss(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d)) return iso;
    var p = function (n) { return String(n).padStart(2, "0"); };
    return p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds());
  }

  function render(data) {
    var items = data.items || [];
    var sig = JSON.stringify(items.map(function (i) { return [i.sym, i.price, i.chg_pct, i.stale]; }));
    if (sig === lastSig) return;          // 无变化不重绘（省电、防闪烁）
    lastSig = sig;

    var up = 0, down = 0, flat = 0, html = "", grp = null;
    items.forEach(function (it) {
      if (it.group !== grp) {
        grp = it.group;
        html += '<div class="grp"><span class="gl">' + grp + '</span></div>';
      }
      var c = cls(it.chg_pct);
      if (c === "up") up++; else if (c === "down") down++; else flat++;
      var mv = hhmmss((it.ts || "").replace(" ", "T"));
      var sub = it.ccy === "GBX" ? (it.name + " · 便士") : it.name;
      html += '<div class="row' + (it.stale ? " stale" : "") + '">' +
        '<div class="id"><div class="sym">' + it.sym + '</div><div class="nm">' + sub + '</div></div>' +
        '<div class="px ' + c + '">' + fmtPrice(it) + '</div>' +
        '<div class="pct ' + c + '">' + fmtChg(it.chg_pct) + '</div>' +
        sparkSVG(it.spark, c) +
        '</div>';
      void mv;
    });
    $list.innerHTML = html || '<div class="error">没有标的</div>';
    $up.textContent = up; $down.textContent = down; $flat.textContent = flat;

    var srcs = data.sources || {};
    var bad = Object.keys(srcs).filter(function (k) { return !srcs[k].ok; });
    var stale = items.filter(function (i) { return i.stale; }).length;
    $dot.className = "dot" + (bad.length ? " err" : (stale ? " warn" : ""));
    var note = "";
    if (bad.length) note = "行情源异常：" + bad.join("/");
    else if (stale) note = stale + " 个标的未更新";
    $note.className = "note" + (bad.length ? " warn" : "");
    $note.textContent = note;
    $stamp.textContent = "更新 " + hhmmss(data.updated_at);
  }

  function load() {
    fetch("/api/quotes", { cache: "no-store" }).then(function (r) {
      return r.json();
    }).then(function (d) {
      render(d);
    }).catch(function (e) {
      $dot.className = "dot err";
      $note.className = "note warn";
      $note.textContent = "行情拉取失败，重试中…";
    });
  }

  function start() {
    load();
    if (timer) clearInterval(timer);
    timer = setInterval(load, 5000);
  }
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) { if (timer) { clearInterval(timer); timer = null; } }
    else start();
  });
  document.getElementById("refresh").addEventListener("click", load);
  start();
})();
