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
    ":host{all:initial;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#172033}",
    ".wrap{position:fixed;right:20px;bottom:20px;z-index:2147483000}",
    ".bubble{width:58px;height:58px;border:0;border-radius:50%;background:#172033;color:#fff;box-shadow:0 14px 40px rgba(23,32,51,.24);cursor:pointer;display:flex;align-items:center;justify-content:center;font:700 20px/1 system-ui}",
    ".bubble:hover{background:#26364f}",
    ".panel{width:min(390px,calc(100vw - 32px));height:min(620px,calc(100vh - 104px));background:#fff;border:1px solid #d9e0ea;border-radius:10px;box-shadow:0 18px 60px rgba(23,32,51,.22);display:flex;flex-direction:column;overflow:hidden}",
    ".head{height:54px;display:flex;align-items:center;justify-content:space-between;padding:0 14px;border-bottom:1px solid #edf1f6;background:#f8fafc}",
    ".title{font:700 15px/1.2 system-ui;color:#172033}",
    ".lesson{font:500 12px/1.2 system-ui;color:#64748b;max-width:270px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px}",
    ".iconbtn{width:32px;height:32px;border:0;border-radius:7px;background:transparent;color:#475569;cursor:pointer;font:700 19px/1 system-ui}",
    ".iconbtn:hover{background:#e9eef5}",
    ".msgs{flex:1;overflow:auto;padding:14px;background:#fff;display:flex;flex-direction:column;gap:11px}",
    ".msg{max-width:86%;padding:10px 12px;border-radius:8px;font:400 14px/1.45 system-ui;white-space:pre-wrap;overflow-wrap:anywhere}",
    ".user{align-self:flex-end;background:#172033;color:#fff}",
    ".assistant{align-self:flex-start;background:#f1f5f9;color:#172033}",
    ".meta{align-self:flex-start;color:#64748b;font:500 12px/1.3 system-ui}",
    ".form{display:flex;gap:8px;padding:12px;border-top:1px solid #edf1f6;background:#f8fafc}",
    ".input{flex:1;resize:none;min-height:42px;max-height:116px;border:1px solid #cbd5e1;border-radius:8px;padding:10px;font:400 14px/1.35 system-ui;outline:none}",
    ".input:focus{border-color:#64748b;box-shadow:0 0 0 3px rgba(100,116,139,.16)}",
    ".send{width:44px;border:0;border-radius:8px;background:#172033;color:#fff;cursor:pointer;font:800 15px/1 system-ui}",
    ".send:disabled{opacity:.45;cursor:not-allowed}",
    ".hidden{display:none!important}",
    "@media(max-width:520px){.wrap{right:12px;bottom:12px}.panel{width:calc(100vw - 24px);height:calc(100vh - 90px)}}",
    "</style>",
    "<div class='wrap hidden' data-wrap>",
    "  <button class='bubble' data-bubble aria-label='Open AI tutor'>AI</button>",
    "  <section class='panel hidden' data-panel aria-label='AI tutor chat'>",
    "    <header class='head'>",
    "      <div><div class='title'>Course tutor</div><div class='lesson' data-lesson></div></div>",
    "      <button class='iconbtn' data-close aria-label='Close tutor'>x</button>",
    "    </header>",
    "    <div class='msgs' data-msgs><div class='meta'>Ask about this lesson.</div></div>",
    "    <form class='form' data-form>",
    "      <textarea class='input' data-input rows='1' placeholder='Ask a question'></textarea>",
    "      <button class='send' data-send type='submit'>></button>",
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
      el.textContent = message.content || "";
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
