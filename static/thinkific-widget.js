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
  };

  var root = document.createElement("div");
  root.id = "towards-ai-thinkific-tutor";
  var shadow = root.attachShadow({ mode: "open" });
  document.documentElement.appendChild(root);

  shadow.innerHTML = [
    "<style>",
    ":host{all:initial;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#182235}",
    ".wrap{position:fixed;right:20px;bottom:20px;z-index:2147483000}",
    ".bubble{height:46px;min-width:142px;border:0;border-radius:999px;background:#182235;color:#fff;box-shadow:0 14px 34px rgba(24,34,53,.28);cursor:pointer;display:flex;align-items:center;justify-content:center;gap:9px;padding:0 16px 0 13px;font:750 14px/1 system-ui;letter-spacing:0}",
    ".bubble:hover{background:#24324b;transform:translateY(-1px)}",
    ".bubble-mark{width:24px;height:24px;border-radius:999px;background:#11b7ba;color:#082c33;display:flex;align-items:center;justify-content:center;font:800 15px/1 system-ui}",
    ".panel{width:min(414px,calc(100vw - 32px));height:min(650px,calc(100vh - 96px));background:#fff;border:1px solid #d7e0ea;border-radius:14px;box-shadow:0 20px 70px rgba(24,34,53,.24);display:flex;flex-direction:column;overflow:hidden}",
    ".head{min-height:68px;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:0 14px 0 16px;border-bottom:1px solid #e7edf4;background:#fbfcfe}",
    ".brand{min-width:0;display:flex;align-items:center;gap:10px}",
    ".brand-mark{width:32px;height:32px;border-radius:8px;background:#182235;color:#fff;display:flex;align-items:center;justify-content:center;font:800 12px/1 system-ui}",
    ".title{font:750 15px/1.2 system-ui;color:#182235;letter-spacing:0}",
    ".lesson{font:600 12px/1.25 system-ui;color:#64748b;max-width:285px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px}",
    ".iconbtn{width:34px;height:34px;flex:0 0 auto;border:0;border-radius:9px;background:#eef3f8;color:#475569;cursor:pointer;font:800 20px/1 system-ui}",
    ".iconbtn:hover{background:#e2eaf3;color:#182235}",
    ".msgs{flex:1;overflow:auto;padding:16px;background:#fff;display:flex;flex-direction:column;gap:12px}",
    ".msg{max-width:88%;padding:11px 13px;border-radius:11px;font:400 14px/1.48 system-ui;overflow-wrap:anywhere}",
    ".user{align-self:flex-end;background:#182235;color:#fff;border-bottom-right-radius:4px}",
    ".assistant{align-self:flex-start;background:#f3f7fb;color:#182235;border:1px solid #e7edf4;border-bottom-left-radius:4px}",
    ".assistant.empty{color:#64748b;font-style:italic}",
    ".md{white-space:normal}",
    ".md p{margin:0 0 10px}",
    ".md p:last-child{margin-bottom:0}",
    ".md ol,.md ul{margin:8px 0 10px 20px;padding:0}",
    ".md li{margin:5px 0;padding-left:2px}",
    ".md a{color:#087e8b;text-decoration:underline;text-underline-offset:2px;font-weight:650}",
    ".md code{background:#e8eef5;border:1px solid #d9e3ee;border-radius:5px;padding:1px 4px;font:500 12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace}",
    ".md pre{margin:8px 0 10px;padding:10px;border-radius:8px;background:#182235;color:#f8fafc;overflow:auto}",
    ".md pre code{background:transparent;border:0;color:inherit;padding:0}",
    ".md strong{font-weight:760}",
    ".meta{align-self:flex-start;color:#64748b;font:600 12px/1.35 system-ui;background:#f8fafc;border:1px solid #edf2f7;border-radius:999px;padding:6px 10px}",
    ".form{display:flex;gap:9px;padding:12px;border-top:1px solid #e7edf4;background:#fbfcfe}",
    ".input{flex:1;resize:none;min-height:44px;max-height:116px;border:1px solid #c8d3df;border-radius:11px;padding:11px 12px;font:400 14px/1.35 system-ui;outline:none;background:#fff;color:#182235}",
    ".input:focus{border-color:#11a7b0;box-shadow:0 0 0 3px rgba(17,167,176,.16)}",
    ".send{width:46px;flex:0 0 46px;border:0;border-radius:11px;background:#182235;color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center}",
    ".send:hover{background:#24324b}",
    ".send:disabled{opacity:.45;cursor:not-allowed}",
    ".send svg{width:18px;height:18px;display:block}",
    ".hidden{display:none!important}",
    "@media(max-width:520px){.wrap{right:12px;bottom:12px}.panel{width:calc(100vw - 24px);height:calc(100vh - 86px)}.lesson{max-width:220px}.bubble{min-width:132px}}",
    "</style>",
    "<div class='wrap hidden' data-wrap>",
    "  <button class='bubble' data-bubble aria-label='Ask the tutor'><span class='bubble-mark'>?</span><span>Ask the tutor</span></button>",
    "  <section class='panel hidden' data-panel aria-label='AI tutor chat'>",
    "    <header class='head'>",
    "      <div class='brand'><div class='brand-mark'>TA</div><div><div class='title'>Towards AI Tutor</div><div class='lesson' data-lesson></div></div></div>",
    "      <button class='iconbtn' data-close aria-label='Minimize tutor' title='Minimize'>&minus;</button>",
    "    </header>",
    "    <div class='msgs' data-msgs><div class='meta'>Ask about this lesson.</div></div>",
    "    <form class='form' data-form>",
    "      <textarea class='input' data-input rows='1' placeholder='Ask about this lesson' data-gramm='false' data-gramm_editor='false' data-enable-grammarly='false'></textarea>",
    "      <button class='send' data-send type='submit' aria-label='Send message'><svg viewBox='0 0 24 24' aria-hidden='true'><path d='M4 12h14M13 6l6 6-6 6' fill='none' stroke='currentColor' stroke-width='2.4' stroke-linecap='round' stroke-linejoin='round'/></svg></button>",
    "    </form>",
    "  </section>",
    "</div>",
  ].join("");

  var wrap = shadow.querySelector("[data-wrap]");
  var bubble = shadow.querySelector("[data-bubble]");
  var panel = shadow.querySelector("[data-panel]");
  var closeBtn = shadow.querySelector("[data-close]");
  var form = shadow.querySelector("[data-form]");
  var input = shadow.querySelector("[data-input]");
  var sendBtn = shadow.querySelector("[data-send]");
  var msgs = shadow.querySelector("[data-msgs]");
  var lessonLabel = shadow.querySelector("[data-lesson]");

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
      var url = new URL(value, window.location.href);
      if (url.protocol === "http:" || url.protocol === "https:") {
        return url.href;
      }
    } catch (_error) {}
    return "";
  }

  function renderBasicMarkdown(text) {
    return escapeHtml(text)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  }

  function renderInlineMarkdown(text) {
    var output = "";
    var lastIndex = 0;
    var linkPattern = /\[([^\]]{1,160})\]\((https?:\/\/[^)\s]+)\)/g;
    var match;
    while ((match = linkPattern.exec(text)) !== null) {
      output += renderBasicMarkdown(text.slice(lastIndex, match.index));
      var href = safeHref(match[2]);
      if (href) {
        output +=
          "<a href='" +
          escapeHtml(href) +
          "' target='_blank' rel='noopener noreferrer'>" +
          renderBasicMarkdown(match[1]) +
          "</a>";
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
    }
  }

  function setOpen(isOpen) {
    state.open = Boolean(isOpen);
    bubble.classList.toggle("hidden", state.open);
    panel.classList.toggle("hidden", !state.open);
    if (state.open) {
      setTimeout(function () {
        input.focus();
      }, 0);
    }
  }

  function renderMessages() {
    msgs.innerHTML = "";
    if (!state.messages.length) {
      var meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = "Ask about this lesson.";
      msgs.appendChild(meta);
    }
    state.messages.forEach(function (message) {
      var el = document.createElement("div");
      el.className = "msg " + (message.role === "user" ? "user" : "assistant");
      if (message.role === "assistant") {
        if (!message.content) {
          el.className += " empty";
          el.textContent = "Thinking...";
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
        setWidgetVisible(Boolean(data && data.eligible));
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
          if (data === "[DONE]") return;
          try {
            handleStreamPart(JSON.parse(data), assistantText);
          } catch (_parseError) {}
        });
      }
    } catch (_error) {
      setLastAssistantContent("The tutor connection failed. Please try again.");
    } finally {
      state.streaming = false;
      sendBtn.disabled = false;
      input.focus();
    }
  }

  bubble.addEventListener("click", function () {
    setOpen(true);
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
    return true;
  }

  var attempts = 0;
  var timer = window.setInterval(function () {
    attempts += 1;
    if (attachCoursePlayerHooks() || attempts > 40) {
      window.clearInterval(timer);
    }
  }, 500);
})();
