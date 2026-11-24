(function () {
  "use strict";

  var script = document.currentScript;
  var apiBase = (
    (script && script.getAttribute("data-api-base")) ||
    window.TOWARDS_AI_TUTOR_API_BASE ||
    ""
  ).replace(/\/+$/, "");
  if (!apiBase && script && script.src) {
    try {
      var scriptUrl = new URL(script.src);
      apiBase = scriptUrl.origin;
    } catch (_error) {
      apiBase = "";
    }
  }
  if (!apiBase) return;

  var state = {
    visible: false,
    open: false,
    context: null,
    threadId: "",
    messages: [],
    streaming: false,
    resolveAbort: null,
    requestId: 0,
    dismissedLesson: "",
  };

  var root = document.createElement("div");
  root.id = "towards-ai-thinkific-tutor";
  var shadow = root.attachShadow({ mode: "open" });
  document.documentElement.appendChild(root);

  shadow.innerHTML = [
    "<style>",
    ":host{all:initial;--font:'Source Sans Pro','Source Sans 3',Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-family:var(--font);color:#1f2340;--brand:#3d47a3;--brand-2:#5662d6;--brand-deep:#2a3180;--ink:#1f2340;--muted:#646a86;--line:rgba(61,71,163,.14);--soft:#f4f5fd}",
    "*{box-sizing:border-box}",
    "button{font:inherit}",
    "button:focus-visible{outline:2px solid var(--brand-2);outline-offset:2px}",
    ".wrap{position:fixed;right:16px;bottom:16px;z-index:2147483000}",
    ".bubble{position:relative;height:48px;border:0;border-radius:999px;background:linear-gradient(135deg,var(--brand-2) 0%,var(--brand) 55%,var(--brand-deep) 100%);color:#fff;box-shadow:0 1px 0 rgba(255,255,255,.28) inset,0 10px 28px rgba(61,71,163,.38),0 2px 6px rgba(31,35,64,.18);cursor:grab;touch-action:none;user-select:none;display:flex;align-items:center;gap:10px;padding:0 18px 0 7px;font:600 15px/1 var(--font);letter-spacing:.1px;transition:transform .2s ease,box-shadow .2s ease;animation:rise .45s cubic-bezier(.2,.8,.2,1) both}",
    ".bubble-x{position:absolute;top:-8px;right:-8px;z-index:1;width:22px;height:22px;border:0;border-radius:999px;background:#fff;color:#646a86;box-shadow:0 2px 8px rgba(31,35,64,.25);display:flex;align-items:center;justify-content:center;padding:5px;cursor:pointer;opacity:0;transition:opacity .15s,transform .15s}",
    ".bubble-x svg{width:12px;height:12px;display:block}",
    ".wrap:hover .bubble-x,.bubble-x:focus-visible{opacity:1}",
    ".bubble-x:hover{color:#1f2340;transform:scale(1.08)}",
    "@media(hover:none){.bubble-x{opacity:1}}",
    ".bubble:hover{transform:translateY(-2px);box-shadow:0 1px 0 rgba(255,255,255,.3) inset,0 16px 36px rgba(61,71,163,.45),0 2px 6px rgba(31,35,64,.18)}",
    ".bubble::after{content:'';position:absolute;inset:-4px;border-radius:999px;border:2px solid rgba(86,98,214,.45);opacity:0;animation:ring 2.4s ease-out .6s 2}",
    ".wrap.dragging .bubble{cursor:grabbing;transform:none}",
    ".bubble-mark{width:34px;height:34px;border-radius:999px;background:rgba(255,255,255,.18);box-shadow:0 0 0 1px rgba(255,255,255,.22) inset;display:flex;align-items:center;justify-content:center}",
    ".bubble-mark svg,.avatar svg,.hello-mark svg{width:18px;height:18px;display:block}",
    ".panel{width:min(416px,calc(100vw - 32px));height:min(640px,calc(100vh - 96px));background:#fbfbff;border:1px solid var(--line);border-radius:20px;box-shadow:0 30px 80px rgba(31,35,64,.22),0 8px 24px rgba(61,71,163,.14);display:flex;flex-direction:column;overflow:hidden;animation:pop .28s cubic-bezier(.2,.8,.2,1) both;transform-origin:bottom right}",
    ".head{min-height:70px;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:0 12px 0 14px;background:linear-gradient(135deg,var(--brand-2) 0%,var(--brand) 60%,var(--brand-deep) 100%);color:#fff;cursor:grab;touch-action:none;user-select:none}",
    ".wrap.dragging .head{cursor:grabbing}",
    ".brand{min-width:0;flex:1 1 auto;display:flex;align-items:center;gap:11px;overflow:hidden}",
    ".avatar{width:38px;height:38px;flex:0 0 38px;border-radius:12px;background:rgba(255,255,255,.16);box-shadow:0 0 0 1px rgba(255,255,255,.24) inset;display:flex;align-items:center;justify-content:center;color:#fff}",
    ".brand-copy{min-width:0;flex:1 1 auto;overflow:hidden}",
    ".title{font:700 16px/1.2 var(--font);letter-spacing:.1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:flex;align-items:center;gap:7px}",
    ".dot{width:7px;height:7px;border-radius:999px;background:#7ef0c3;box-shadow:0 0 0 3px rgba(126,240,195,.22)}",
    ".lesson{font:400 13px/1.25 var(--font);color:rgba(255,255,255,.78);max-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px}",
    ".actions{display:flex;align-items:center;gap:6px;flex:0 0 auto}",
    ".iconbtn{width:34px;height:34px;flex:0 0 auto;border:0;border-radius:10px;background:rgba(255,255,255,.14);color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:background .15s}",
    ".iconbtn:hover{background:rgba(255,255,255,.26)}",
    ".iconbtn svg{width:17px;height:17px;display:block}",
    ".msgs{flex:1;overflow:auto;padding:18px 16px;background:linear-gradient(180deg,#f6f7fe 0%,#fbfbff 140px);display:flex;flex-direction:column;gap:12px;scroll-behavior:smooth}",
    ".msg{max-width:86%;padding:11px 14px;border-radius:16px;font:400 15px/1.5 var(--font);overflow-wrap:anywhere;animation:fade .25s ease both}",
    ".user{align-self:flex-end;background:linear-gradient(135deg,var(--brand-2),var(--brand));color:#fff;border-bottom-right-radius:5px;box-shadow:0 6px 16px rgba(61,71,163,.22)}",
    ".assistant{align-self:flex-start;background:#fff;color:var(--ink);border:1px solid var(--line);border-bottom-left-radius:5px;box-shadow:0 4px 14px rgba(31,35,64,.05)}",
    ".assistant.empty{color:var(--muted);display:flex;align-items:center;gap:4px}",
    ".assistant.empty i{width:6px;height:6px;border-radius:999px;background:var(--brand-2);opacity:.35;animation:blink 1.2s infinite}",
    ".assistant.empty i:nth-child(2){animation-delay:.15s}",
    ".assistant.empty i:nth-child(3){animation-delay:.3s}",
    ".md{white-space:normal}",
    ".md p{margin:0 0 10px}",
    ".md p:last-child{margin-bottom:0}",
    ".md ol,.md ul{margin:8px 0 10px 20px;padding:0}",
    ".md li{margin:5px 0;padding-left:2px}",
    ".md a{color:var(--brand);text-decoration:underline;text-underline-offset:2px;font-weight:600}",
    ".md code{background:var(--soft);border:1px solid var(--line);border-radius:6px;padding:1px 5px;font:500 12.5px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace}",
    ".md pre{margin:8px 0 10px;padding:12px;border-radius:12px;background:#1f2340;color:#f4f5ff;overflow:auto}",
    ".md pre code{background:transparent;border:0;color:inherit;padding:0}",
    ".md strong{font-weight:700}",
    ".hello{display:flex;flex-direction:column;align-items:flex-start;gap:10px;padding:4px 2px;animation:fade .3s ease both}",
    ".hello-mark{width:42px;height:42px;border-radius:14px;background:linear-gradient(135deg,var(--brand-2),var(--brand));color:#fff;display:flex;align-items:center;justify-content:center;box-shadow:0 8px 20px rgba(61,71,163,.28)}",
    ".hello-title{font:700 17px/1.3 var(--font);color:var(--ink)}",
    ".hello-sub{font:400 14px/1.45 var(--font);color:var(--muted);margin-top:-4px}",
    ".chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:4px}",
    ".chip{border:1px solid var(--line);background:#fff;color:var(--brand);border-radius:999px;padding:8px 13px;font:600 13.5px/1 var(--font);cursor:pointer;transition:background .15s,border-color .15s,transform .15s}",
    ".chip:hover{background:var(--soft);border-color:rgba(61,71,163,.32);transform:translateY(-1px)}",
    ".form{display:flex;align-items:flex-end;gap:8px;margin:0 12px 12px;padding:6px 6px 6px 14px;border:1px solid var(--line);border-radius:16px;background:#fff;box-shadow:0 6px 18px rgba(31,35,64,.06);transition:border-color .15s,box-shadow .15s}",
    ".form:focus-within{border-color:rgba(61,71,163,.45);box-shadow:0 0 0 4px rgba(86,98,214,.12),0 6px 18px rgba(31,35,64,.06)}",
    ".input{flex:1;resize:none;min-height:40px;max-height:116px;border:0;padding:10px 0;font:400 15px/1.35 var(--font);outline:none;background:transparent;color:var(--ink)}",
    ".input::placeholder{color:#9aa0bb}",
    ".send{width:40px;height:40px;flex:0 0 40px;border:0;border-radius:12px;background:linear-gradient(135deg,var(--brand-2),var(--brand));color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 6px 14px rgba(61,71,163,.3);transition:transform .15s,opacity .15s}",
    ".send:hover{transform:translateY(-1px)}",
    ".send:disabled{opacity:.4;cursor:not-allowed;transform:none;box-shadow:none}",
    ".send svg{width:18px;height:18px;display:block}",
    ".foot{font:400 11.5px/1 var(--font);color:#9aa0bb;text-align:center;margin:-4px 0 10px}",
    ".hidden{display:none!important}",
    "@keyframes rise{from{opacity:0;transform:translateY(12px) scale(.96)}to{opacity:1;transform:none}}",
    "@keyframes pop{from{opacity:0;transform:translateY(10px) scale(.97)}to{opacity:1;transform:none}}",
    "@keyframes fade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}",
    "@keyframes ring{0%{opacity:.9;transform:scale(1)}100%{opacity:0;transform:scale(1.25)}}",
    "@keyframes blink{0%,80%,100%{opacity:.25}40%{opacity:.9}}",
    "@media(prefers-reduced-motion:reduce){*,*::after{animation:none!important;transition:none!important}}",
    "@media(max-width:520px){.wrap{right:12px;bottom:12px}.panel{width:calc(100vw - 24px);height:calc(100vh - 86px)}.lesson{max-width:210px}}",
    "</style>",
    "<div class='wrap hidden' data-wrap>",
    "  <button class='bubble-x' data-dismiss aria-label='Hide the tutor for this lesson' title='Hide for this lesson'><svg viewBox='0 0 24 24' aria-hidden='true'><path d='M7 7l10 10M17 7L7 17' fill='none' stroke='currentColor' stroke-width='2.6' stroke-linecap='round'/></svg></button><button class='bubble' data-bubble aria-label='Ask the tutor'><span class='bubble-mark'><svg viewBox='0 0 24 24' aria-hidden='true'><path d='M12 3.5c.5 3.9 2.6 6 6.5 6.5-3.9.5-6 2.6-6.5 6.5-.5-3.9-2.6-6-6.5-6.5 3.9-.5 6-2.6 6.5-6.5z' fill='currentColor'/><path d='M18.5 15.5c.2 1.6 1 2.4 2.5 2.5-1.5.2-2.3 1-2.5 2.5-.2-1.5-1-2.3-2.5-2.5 1.5-.1 2.3-.9 2.5-2.5z' fill='currentColor' opacity='.7'/></svg></span><span>Ask the tutor</span></button>",
    "  <section class='panel hidden' data-panel aria-label='AI tutor chat'>",
    "    <header class='head' data-drag-handle title='Drag to move tutor'>",
    "      <div class='brand'><div class='avatar'><svg viewBox='0 0 24 24' aria-hidden='true'><path d='M12 3.5c.5 3.9 2.6 6 6.5 6.5-3.9.5-6 2.6-6.5 6.5-.5-3.9-2.6-6-6.5-6.5 3.9-.5 6-2.6 6.5-6.5z' fill='currentColor'/><path d='M18.5 15.5c.2 1.6 1 2.4 2.5 2.5-1.5.2-2.3 1-2.5 2.5-.2-1.5-1-2.3-2.5-2.5 1.5-.1 2.3-.9 2.5-2.5z' fill='currentColor' opacity='.7'/></svg></div><div class='brand-copy'><div class='title'>Towards AI Tutor<span class='dot' aria-hidden='true'></span></div><div class='lesson' data-lesson></div></div></div>",
    "      <div class='actions'><button class='iconbtn' data-reset aria-label='Restart conversation' title='Restart conversation'><svg viewBox='0 0 24 24' aria-hidden='true'><path d='M3 3v6h6' fill='none' stroke='currentColor' stroke-width='2.3' stroke-linecap='round' stroke-linejoin='round'/><path d='M3.8 13.1a8 8 0 1 0 2.3-7.2L3 9' fill='none' stroke='currentColor' stroke-width='2.3' stroke-linecap='round' stroke-linejoin='round'/></svg></button><button class='iconbtn' data-close aria-label='Minimize tutor' title='Minimize'><svg viewBox='0 0 24 24' aria-hidden='true'><path d='M6 12h12' fill='none' stroke='currentColor' stroke-width='2.4' stroke-linecap='round'/></svg></button></div>",
    "    </header>",
    "    <div class='msgs' data-msgs></div>",
    "    <form class='form' data-form>",
    "      <textarea class='input' data-input rows='1' placeholder='Ask about this lesson' data-gramm='false' data-gramm_editor='false' data-enable-grammarly='false'></textarea>",
    "      <button class='send' data-send type='submit' aria-label='Send message'><svg viewBox='0 0 24 24' aria-hidden='true'><path d='M4 12h14M13 6l6 6-6 6' fill='none' stroke='currentColor' stroke-width='2.4' stroke-linecap='round' stroke-linejoin='round'/></svg></button>",
    "    </form>",
    "    <div class='foot'>Answers come from this course's material.</div>",
    "  </section>",
    "</div>",
  ].join("");

  var SPARKLE = "<svg viewBox='0 0 24 24' aria-hidden='true'><path d='M12 3.5c.5 3.9 2.6 6 6.5 6.5-3.9.5-6 2.6-6.5 6.5-.5-3.9-2.6-6-6.5-6.5 3.9-.5 6-2.6 6.5-6.5z' fill='currentColor'/><path d='M18.5 15.5c.2 1.6 1 2.4 2.5 2.5-1.5.2-2.3 1-2.5 2.5-.2-1.5-1-2.3-2.5-2.5 1.5-.1 2.3-.9 2.5-2.5z' fill='currentColor' opacity='.7'/></svg>";
  var STARTERS = ["Summarize this lesson", "Explain the key idea simply", "Quiz me on this lesson"];

  var wrap = shadow.querySelector("[data-wrap]");
  var bubble = shadow.querySelector("[data-bubble]");
  var dismissBtn = shadow.querySelector("[data-dismiss]");
  var panel = shadow.querySelector("[data-panel]");
  var dragHandle = shadow.querySelector("[data-drag-handle]");
  var resetBtn = shadow.querySelector("[data-reset]");
  var closeBtn = shadow.querySelector("[data-close]");
  var form = shadow.querySelector("[data-form]");
  var input = shadow.querySelector("[data-input]");
  var sendBtn = shadow.querySelector("[data-send]");
  var msgs = shadow.querySelector("[data-msgs]");
  var lessonLabel = shadow.querySelector("[data-lesson]");
  var positionStorageKey = "towards-ai-thinkific-tutor-position-v3";
  var customPosition = false;
  var minimizedPosition = null;
  var minimizedUsesDefaultAnchor = true;
  var suppressBubbleClick = false;

  function readSavedPosition() {
    try {
      var parsed = JSON.parse(window.localStorage.getItem(positionStorageKey) || "null");
      if (
        parsed &&
        Number.isFinite(parsed.left) &&
        Number.isFinite(parsed.top)
      ) {
        return { left: parsed.left, top: parsed.top };
      }
    } catch (_error) {}
    return null;
  }

  function viewportSize() {
    return {
      width: Math.max(
        document.documentElement.clientWidth || 0,
        window.innerWidth || 0,
      ),
      height: Math.max(
        document.documentElement.clientHeight || 0,
        window.innerHeight || 0,
      ),
    };
  }

  function clampCoordinates(left, top, width, height) {
    var margin = 12;
    var viewport = viewportSize();
    var maxLeft = Math.max(margin, viewport.width - width - margin);
    var maxTop = Math.max(margin, viewport.height - height - margin);
    return {
      left: Math.min(Math.max(left, margin), maxLeft),
      top: Math.min(Math.max(top, margin), maxTop),
    };
  }

  function positionWrap(left, top) {
    wrap.style.left = Math.round(left) + "px";
    wrap.style.top = Math.round(top) + "px";
    wrap.style.right = "auto";
    wrap.style.bottom = "auto";
  }

  function positionWrapAtDefault() {
    wrap.style.left = "";
    wrap.style.top = "";
    wrap.style.right = "";
    wrap.style.bottom = "";
  }

  function clampToViewport() {
    if (!customPosition || wrap.classList.contains("hidden")) return;
    var rect = wrap.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    var clamped = clampCoordinates(rect.left, rect.top, rect.width, rect.height);
    positionWrap(clamped.left, clamped.top);
  }

  function saveMinimizedPosition() {
    if (
      !customPosition ||
      state.open ||
      wrap.classList.contains("hidden")
    ) {
      return;
    }
    var rect = wrap.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    minimizedPosition = {
      left: Math.round(rect.left),
      top: Math.round(rect.top),
    };
    minimizedUsesDefaultAnchor = false;
    try {
      window.localStorage.setItem(
        positionStorageKey,
        JSON.stringify(minimizedPosition),
      );
    } catch (_error) {}
  }

  function restoreMinimizedPosition() {
    var saved = minimizedPosition || readSavedPosition();
    if (!saved) return false;
    minimizedPosition = { left: saved.left, top: saved.top };
    minimizedUsesDefaultAnchor = false;
    customPosition = true;
    positionWrap(saved.left, saved.top);
    window.requestAnimationFrame(function () {
      clampToViewport();
      saveMinimizedPosition();
    });
    return true;
  }

  function rememberMinimizedAnchor() {
    if (customPosition) {
      saveMinimizedPosition();
      return;
    }
    minimizedPosition = null;
    minimizedUsesDefaultAnchor = true;
  }

  function restoreMinimizedAnchor() {
    if (minimizedUsesDefaultAnchor || !minimizedPosition) {
      customPosition = false;
      positionWrapAtDefault();
      return;
    }
    customPosition = true;
    positionWrap(minimizedPosition.left, minimizedPosition.top);
  }

  function beginDrag(event, options) {
    options = options || {};
    if (!state.visible) return;
    if (event.pointerType === "mouse" && event.button !== 0) return;
    if (
      options.ignoreActions &&
      event.target &&
      typeof event.target.closest === "function" &&
      event.target.closest(".actions")
    ) {
      return;
    }

    var rect = wrap.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    var pointerId = event.pointerId;
    var dragTarget = event.currentTarget;
    var capturedPointer = false;
    try {
      if (dragTarget && typeof dragTarget.setPointerCapture === "function") {
        dragTarget.setPointerCapture(pointerId);
        capturedPointer = true;
      }
    } catch (_error) {}
    var startX = event.clientX;
    var startY = event.clientY;
    var startLeft = rect.left;
    var startTop = rect.top;
    var moved = false;

    function onPointerMove(moveEvent) {
      if (moveEvent.pointerId !== pointerId) return;
      var deltaX = moveEvent.clientX - startX;
      var deltaY = moveEvent.clientY - startY;
      if (!moved && Math.abs(deltaX) + Math.abs(deltaY) < 6) return;
      moved = true;
      customPosition = true;
      if (!state.open) minimizedUsesDefaultAnchor = false;
      wrap.classList.add("dragging");
      var clamped = clampCoordinates(
        startLeft + deltaX,
        startTop + deltaY,
        rect.width,
        rect.height,
      );
      positionWrap(clamped.left, clamped.top);
      moveEvent.preventDefault();
    }

    function finishDrag(endEvent) {
      if (endEvent.pointerId !== pointerId) return;
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", finishDrag);
      window.removeEventListener("pointercancel", finishDrag);
      try {
        if (
          capturedPointer &&
          dragTarget &&
          typeof dragTarget.hasPointerCapture === "function" &&
          dragTarget.hasPointerCapture(pointerId)
        ) {
          dragTarget.releasePointerCapture(pointerId);
        }
      } catch (_error) {}
      wrap.classList.remove("dragging");
      if (!moved) return;
      saveMinimizedPosition();
      if (typeof options.onMoved === "function") options.onMoved();
    }

    window.addEventListener("pointermove", onPointerMove, { passive: false });
    window.addEventListener("pointerup", finishDrag);
    window.addEventListener("pointercancel", finishDrag);
  }

  function safeString(value) {
    if (value === null || value === undefined) return "";
    return String(value);
  }

  function escapeHtml(value) {
    return safeString(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function safeHref(value) {
    try {
      var candidate = safeString(value).trim();
      if (/^www\./i.test(candidate)) candidate = "https://" + candidate;
      var url = new URL(candidate, window.location.href);
      if (url.protocol === "http:" || url.protocol === "https:") {
        return url.href;
      }
    } catch (_error) {}
    return "";
  }

  function displayUrl(value) {
    return safeString(value).replace(/^https?:\/\//i, "").replace(/\/$/, "");
  }

  function splitTrailingUrlPunctuation(value) {
    var url = safeString(value);
    var suffix = "";
    while (/[.,;:!?]$/.test(url)) {
      suffix = url.slice(-1) + suffix;
      url = url.slice(0, -1);
    }
    while (
      url.slice(-1) === ")" &&
      (url.match(/\)/g) || []).length > (url.match(/\(/g) || []).length
    ) {
      suffix = ")" + suffix;
      url = url.slice(0, -1);
    }
    return { url: url, suffix: suffix };
  }

  function renderBasicMarkdown(text) {
    return escapeHtml(text)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  }

  function renderInlineMarkdown(text) {
    var output = "";
    var lastIndex = 0;
    var linkPattern =
      /\[([^\]]{1,180})\]\(((?:https?:\/\/|www\.)[^)\s]+)\)|\[((?:https?:\/\/|www\.)[^\]\s]+)\]|((?:https?:\/\/|www\.)[^\s<]+)/g;
    var match;
    while ((match = linkPattern.exec(text)) !== null) {
      output += renderBasicMarkdown(text.slice(lastIndex, match.index));
      var rawUrl = match[2] || match[3] || match[4] || "";
      var suffix = "";
      if (!match[2]) {
        var splitUrl = splitTrailingUrlPunctuation(rawUrl);
        rawUrl = splitUrl.url;
        suffix = splitUrl.suffix;
      }
      var href = safeHref(rawUrl);
      if (href) {
        output +=
          "<a href='" +
          escapeHtml(href) +
          "' target='_blank' rel='noopener noreferrer'>" +
          (match[1] ? renderBasicMarkdown(match[1]) : escapeHtml(displayUrl(rawUrl))) +
          "</a>";
        if (suffix) output += renderBasicMarkdown(suffix);
      } else {
        output += renderBasicMarkdown(match[0]);
      }
      lastIndex = match.index + match[0].length;
    }
    output += renderBasicMarkdown(text.slice(lastIndex));
    return output;
  }

  function isListLine(line) {
    return /^\s*(?:[-*]\s+|\d+\.\s+)/.test(line);
  }

  function isHeadingLine(line) {
    return /^\s*#{1,4}\s+/.test(line);
  }

  function renderMarkdown(markdown) {
    var lines = safeString(markdown).replace(/\r\n/g, "\n").split("\n");
    var html = [];
    var index = 0;

    while (index < lines.length) {
      var line = lines[index];
      var trimmed = line.trim();
      if (!trimmed) {
        index += 1;
        continue;
      }

      if (trimmed.indexOf("```") === 0) {
        var code = [];
        index += 1;
        while (index < lines.length && lines[index].trim().indexOf("```") !== 0) {
          code.push(lines[index]);
          index += 1;
        }
        if (index < lines.length) index += 1;
        html.push("<pre><code>" + escapeHtml(code.join("\n")) + "</code></pre>");
        continue;
      }

      if (isHeadingLine(line)) {
        html.push(
          "<p><strong>" +
            renderInlineMarkdown(trimmed.replace(/^#{1,4}\s+/, "")) +
            "</strong></p>",
        );
        index += 1;
        continue;
      }

      if (isListLine(line)) {
        var ordered = /^\s*\d+\.\s+/.test(line);
        var tag = ordered ? "ol" : "ul";
        var items = [];
        while (
          index < lines.length &&
          isListLine(lines[index]) &&
          /^\s*\d+\.\s+/.test(lines[index]) === ordered
        ) {
          items.push(
            "<li>" +
              renderInlineMarkdown(
                lines[index].replace(/^\s*(?:[-*]\s+|\d+\.\s+)/, ""),
              ) +
              "</li>",
          );
          index += 1;
        }
        html.push("<" + tag + ">" + items.join("") + "</" + tag + ">");
        continue;
      }

      var paragraph = [trimmed];
      index += 1;
      while (
        index < lines.length &&
        lines[index].trim() &&
        lines[index].trim().indexOf("```") !== 0 &&
        !isListLine(lines[index]) &&
        !isHeadingLine(lines[index])
      ) {
        paragraph.push(lines[index].trim());
        index += 1;
      }
      html.push("<p>" + renderInlineMarkdown(paragraph.join(" ")) + "</p>");
    }

    return "<div class='md'>" + html.join("") + "</div>";
  }

  function entityFrom(raw) {
    raw = raw || {};
    return {
      id: raw.id || raw.course_id || raw.chapter_id || raw.lesson_id || "",
      title: raw.title || raw.name || "",
      name: raw.name || raw.title || "",
      slug: raw.slug || "",
      type: raw.type || "",
      kind: raw.kind || "",
      contentType: raw.contentType || raw.content_type || "",
      content_type: raw.content_type || raw.contentType || "",
      lessonType: raw.lessonType || raw.lesson_type || "",
      lesson_type: raw.lesson_type || raw.lessonType || "",
    };
  }

  function pickUser(rawUser) {
    var user = rawUser || (window.Thinkific && window.Thinkific.current_user) || {};
    return {
      id: user.id || "",
      email: user.email || "",
      firstName: user.first_name || user.firstName || "",
      lastName: user.last_name || user.lastName || "",
    };
  }

  function visibleText() {
    var candidate =
      document.querySelector("[data-lesson-content]") ||
      document.querySelector(".course-player__content") ||
      document.querySelector("main") ||
      document.body;
    return safeString(candidate && candidate.innerText).replace(/\s+\n/g, "\n").trim().slice(0, 12000);
  }

  function buildContext(hookData) {
    hookData = hookData || {};
    return {
      url: window.location.href,
      origin: window.location.origin,
      referrer: document.referrer || "",
      pageTitle: document.title || "",
      course: entityFrom(hookData.course),
      chapter: entityFrom(hookData.chapter),
      lesson: entityFrom(hookData.lesson),
      enrollment: hookData.enrollment || {},
      user: pickUser(hookData.user),
      selectedText: safeString(window.getSelection && window.getSelection()).slice(0, 4000),
      pageText: visibleText(),
      extra: {
        pathname: window.location.pathname,
        lessonContentUrls: [
          hookData.lesson && hookData.lesson.url,
          hookData.lesson && hookData.lesson.sourceUrl,
          hookData.lesson && hookData.lesson.source_url,
          hookData.lesson && hookData.lesson.contentUrl,
          hookData.lesson && hookData.lesson.content_url,
        ].concat(Array.prototype.map.call(document.querySelectorAll("iframe[src]"), function (frame) {
          return frame.src;
        })).filter(function (url) { return typeof url === "string" && /^https:\/\//i.test(url); }).slice(0, 12),
        contentType:
          safeString(hookData.lesson && (hookData.lesson.contentType || hookData.lesson.content_type)),
        lessonType:
          safeString(hookData.lesson && (hookData.lesson.lessonType || hookData.lesson.lesson_type || hookData.lesson.type)),
      },
    };
  }

  function hasLesson(context) {
    var lesson = context && context.lesson;
    return Boolean(lesson && (lesson.id || lesson.title || lesson.name || lesson.slug));
  }

  function hasLoggedInUser(context) {
    var user = context && context.user;
    var enrollment = (context && context.enrollment) || {};
    return Boolean(
      (user && (user.id || user.email)) ||
        enrollment.user_id ||
        enrollment.userId ||
        enrollment.student_id ||
        enrollment.studentId
    );
  }

  function normalized(value) {
    return safeString(value).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  }

  function isBlockedLesson(context) {
    var lesson = (context && context.lesson) || {};
    var extra = (context && context.extra) || {};
    var text = normalized(
      [
        lesson.type,
        lesson.kind,
        lesson.contentType,
        lesson.content_type,
        lesson.lessonType,
        lesson.lesson_type,
        lesson.title,
        lesson.name,
        lesson.slug,
        context && context.pageTitle,
        extra.pathname,
      ].join(" "),
    );
    return ["quiz", "quizz", "exam", "assessment"].some(function (keyword) {
      return text.indexOf(keyword) !== -1;
    });
  }

  function setWidgetVisible(isVisible) {
    state.visible = Boolean(isVisible);
    wrap.classList.toggle("hidden", !state.visible);
    if (!state.visible) {
      setOpen(false);
    } else if (!customPosition) {
      restoreMinimizedPosition();
    } else {
      window.requestAnimationFrame(clampToViewport);
    }
  }

  function setOpen(isOpen) {
    var nextOpen = Boolean(isOpen);
    var wasOpen = state.open;
    if (nextOpen && !wasOpen) rememberMinimizedAnchor();
    state.open = nextOpen;
    bubble.classList.toggle("hidden", state.open);
    dismissBtn.classList.toggle("hidden", state.open);
    panel.classList.toggle("hidden", !state.open);
    if (!state.open && wasOpen) restoreMinimizedAnchor();
    window.requestAnimationFrame(function () {
      clampToViewport();
      if (!state.open) saveMinimizedPosition();
      if (state.open) input.focus();
    });
  }

  function renderMessages() {
    msgs.innerHTML = "";
    if (!state.messages.length) {
      msgs.innerHTML =
        "<div class='hello'><div class='hello-mark'>" + SPARKLE + "</div>" +
        "<div class='hello-title'>Hi! Ask me anything about this lesson.</div>" +
        "<div class='hello-sub'>I answer from the course material, so you can go deeper without leaving the page.</div>" +
        "<div class='chips'>" +
        STARTERS.map(function (q) {
          return "<button type='button' class='chip' data-prompt='" + escapeHtml(q) + "'>" + escapeHtml(q) + "</button>";
        }).join("") +
        "</div></div>";
    }
    state.messages.forEach(function (message) {
      var el = document.createElement("div");
      el.className = "msg " + (message.role === "user" ? "user" : "assistant");
      if (message.role === "assistant") {
        if (!message.content) {
          el.className += " empty";
          el.setAttribute("aria-label", "Thinking");
          el.innerHTML = "<i></i><i></i><i></i>";
        } else {
          el.innerHTML = renderMarkdown(message.content);
        }
      } else {
        el.textContent = message.content || "";
      }
      msgs.appendChild(el);
    });
    msgs.scrollTop = msgs.scrollHeight;
  }

  function updateLessonLabel(context) {
    var lesson = context && context.lesson;
    var course = context && context.course;
    var label = "";
    if (lesson && (lesson.title || lesson.name)) label = lesson.title || lesson.name;
    if (!label && course && (course.title || course.name)) label = course.title || course.name;
    lessonLabel.textContent = label;
  }

  function lessonKey(context) {
    var lesson = (context && context.lesson) || {};
    return String(lesson.id || lesson.slug || lesson.title || (context && context.url) || "");
  }

  function resolveEligibility(context) {
    if (!hasLesson(context) || !hasLoggedInUser(context) || isBlockedLesson(context)) {
      setWidgetVisible(false);
      return;
    }
    if (state.resolveAbort) state.resolveAbort.abort();
    state.resolveAbort = new AbortController();
    fetch(apiBase + "/api/thinkific/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ context: context }),
      signal: state.resolveAbort.signal,
    })
      .then(function (response) {
        if (!response.ok) return { eligible: false };
        return response.json();
      })
      .then(function (data) {
        state.context = context;
        updateLessonLabel(context);
        if (state.dismissedLesson && state.dismissedLesson !== lessonKey(context)) state.dismissedLesson = "";
        setWidgetVisible(Boolean(data && data.eligible) && !state.dismissedLesson);
      })
      .catch(function (error) {
        if (error && error.name === "AbortError") return;
        setWidgetVisible(false);
      });
  }

  function addMessage(role, content) {
    state.messages.push({ role: role, content: content });
    if (state.messages.length > 16) {
      state.messages = state.messages.slice(state.messages.length - 16);
    }
    renderMessages();
  }

  function setLastAssistantContent(content) {
    var last = state.messages[state.messages.length - 1];
    if (!last || last.role !== "assistant") {
      state.messages.push({ role: "assistant", content: "" });
      last = state.messages[state.messages.length - 1];
    }
    last.content = content;
    renderMessages();
  }

  function historyForRequest() {
    return state.messages
      .filter(function (message) {
        return message.role === "user" || message.role === "assistant";
      })
      .slice(-12);
  }

  function resetConversation() {
    state.requestId += 1;
    state.threadId = "";
    state.messages = [];
    state.streaming = false;
    sendBtn.disabled = false;
    input.value = "";
    input.style.height = "42px";
    renderMessages();
    input.focus();
  }

  function parseSseFrames(buffer, onFrame) {
    var boundary;
    while ((boundary = buffer.indexOf("\n\n")) >= 0) {
      var frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      var dataLines = frame
        .split("\n")
        .filter(function (line) {
          return line.indexOf("data:") === 0;
        })
        .map(function (line) {
          return line.slice(5).trimStart();
        });
      if (dataLines.length) onFrame(dataLines.join("\n"));
    }
    return buffer;
  }

  function handleStreamPart(part, assistantText) {
    if (part.type === "data-thread" && part.data && part.data.threadId) {
      state.threadId = part.data.threadId;
    } else if (part.type === "text-delta") {
      assistantText.value += part.delta || "";
      setLastAssistantContent(assistantText.value);
    } else if (part.type === "error") {
      assistantText.value = part.errorText || "The tutor could not answer.";
      setLastAssistantContent(assistantText.value);
    }
  }

  async function sendQuestion(question) {
    if (state.streaming || !question.trim() || !state.context) return;
    var requestId = ++state.requestId;
    state.streaming = true;
    sendBtn.disabled = true;
    addMessage("user", question);
    setLastAssistantContent("");

    var assistantText = { value: "" };
    var response;
    try {
      response = await fetch(apiBase + "/api/thinkific/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: question,
          history: historyForRequest().slice(0, -2),
          threadId: state.threadId,
          context: state.context,
        }),
      });
      if (requestId !== state.requestId) return;
      if (!response.ok || !response.body) {
        var errorText = "The tutor is not available for this lesson.";
        try {
          var payload = await response.json();
          errorText = payload.detail || errorText;
        } catch (_jsonError) {}
        setLastAssistantContent(errorText);
        return;
      }

      var reader = response.body.getReader();
      var decoder = new TextDecoder();
      var buffer = "";
      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true });
        buffer = parseSseFrames(buffer, function (data) {
          if (requestId !== state.requestId) return;
          if (data === "[DONE]") return;
          try {
            handleStreamPart(JSON.parse(data), assistantText);
          } catch (_parseError) {}
        });
      }
    } catch (_error) {
      if (requestId !== state.requestId) return;
      setLastAssistantContent("The tutor connection failed. Please try again.");
    } finally {
      if (requestId !== state.requestId) return;
      state.streaming = false;
      sendBtn.disabled = false;
      input.focus();
    }
  }

  bubble.addEventListener("pointerdown", function (event) {
    beginDrag(event, {
      onMoved: function () {
        suppressBubbleClick = true;
        window.setTimeout(function () {
          suppressBubbleClick = false;
        }, 0);
      },
    });
  });
  dragHandle.addEventListener("pointerdown", function (event) {
    beginDrag(event, { ignoreActions: true });
  });
  dismissBtn.addEventListener("click", function (event) {
    event.stopPropagation();
    state.dismissedLesson = lessonKey(state.context);
    setWidgetVisible(false);
  });
  bubble.addEventListener("click", function () {
    if (suppressBubbleClick) {
      suppressBubbleClick = false;
      return;
    }
    setOpen(true);
  });
  resetBtn.addEventListener("click", resetConversation);
  msgs.addEventListener("click", function (event) {
    var chip = event.target && event.target.closest ? event.target.closest("[data-prompt]") : null;
    if (!chip || state.streaming) return;
    sendQuestion(chip.getAttribute("data-prompt"));
  });
  closeBtn.addEventListener("click", function () {
    setOpen(false);
  });
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var question = input.value.trim();
    if (!question) return;
    input.value = "";
    input.style.height = "42px";
    sendQuestion(question);
  });
  input.addEventListener("input", function () {
    input.style.height = "42px";
    input.style.height = Math.min(input.scrollHeight, 116) + "px";
  });
  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.dispatchEvent(new Event("submit", { cancelable: true }));
    }
  });
  window.addEventListener("resize", function () {
    if (!customPosition) return;
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(function () {
        clampToViewport();
        saveMinimizedPosition();
      });
    });
  });
  if (typeof window.ResizeObserver === "function") {
    new window.ResizeObserver(function () {
      if (!customPosition || wrap.classList.contains("hidden")) return;
      window.requestAnimationFrame(function () {
        clampToViewport();
        saveMinimizedPosition();
      });
    }).observe(wrap);
  }

  function attachCoursePlayerHooks() {
    if (!window.CoursePlayerV2 || typeof window.CoursePlayerV2.on !== "function") {
      setWidgetVisible(false);
      return false;
    }
    window.CoursePlayerV2.on("hooks:contentDidChange", function (data) {
      resolveEligibility(buildContext(data));
    });
    window.CoursePlayerV2.on("hooks:contentWasCompleted", function (data) {
      state.context = buildContext(data);
      updateLessonLabel(state.context);
    });
    if (!state.context) {
      var fromUrl = hookDataFromUrl();
      if (fromUrl) resolveEligibility(buildContext(fromUrl));
    }
    return true;
  }

  function hookDataFromUrl() {
    var match = window.location.pathname.match(/\/courses\/take\/([^/]+)\/([^/]+)\/(\d+)-([^/?#]+)/);
    if (!match) return null;
    var header = document.querySelector(".course-player__content-header__title, [class*='content-header__title']");
    return {
      course: { slug: match[1] },
      lesson: {
        id: match[3],
        slug: match[4],
        title: safeString(header && header.textContent).trim() || match[4].replace(/-/g, " "),
        contentType: match[2],
      },
    };
  }

  renderMessages();

  var attempts = 0;
  var timer = window.setInterval(function () {
    attempts += 1;
    if (attachCoursePlayerHooks() || attempts > 40) {
      window.clearInterval(timer);
    }
  }, 500);
})();
