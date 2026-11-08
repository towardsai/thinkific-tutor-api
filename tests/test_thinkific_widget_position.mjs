import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";


class FakeClassList {
  constructor(...tokens) {
    this.tokens = new Set(tokens);
  }

  add(token) {
    this.tokens.add(token);
  }

  remove(token) {
    this.tokens.delete(token);
  }

  contains(token) {
    return this.tokens.has(token);
  }

  toggle(token, force) {
    const shouldAdd = force === undefined ? !this.contains(token) : Boolean(force);
    if (shouldAdd) this.add(token);
    else this.remove(token);
    return shouldAdd;
  }
}


class FakeElement {
  constructor(...classes) {
    this.classList = new FakeClassList(...classes);
    this.style = {};
    this.listeners = new Map();
    this.children = [];
    this.value = "";
    this.innerHTML = "";
    this.innerText = "";
    this.textContent = "";
    this.scrollHeight = 0;
    this.scrollTop = 0;
    this.capturedPointers = new Set();
  }

  addEventListener(type, listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(listener);
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  closest() {
    return null;
  }

  dispatch(type, details = {}) {
    const event = {
      preventDefault() {},
      target: this,
      ...details,
      currentTarget: this,
    };
    for (const listener of this.listeners.get(type) || []) listener(event);
  }

  dispatchEvent(event) {
    this.dispatch(event.type, event);
    return true;
  }

  focus() {}

  hasPointerCapture(pointerId) {
    return this.capturedPointers.has(pointerId);
  }

  releasePointerCapture(pointerId) {
    this.capturedPointers.delete(pointerId);
  }

  setPointerCapture(pointerId) {
    this.capturedPointers.add(pointerId);
  }
}


async function createWidgetHarness({ frames = [] } = {}) {
  const viewport = { width: 1000, height: 800 };
  const storage = new Map();
  const courseHooks = new Map();
  const requests = [];
  const windowListeners = new Map();
  let resizeObserverCallback = () => {};

  const wrap = new FakeElement("wrap", "hidden");
  const bubble = new FakeElement("bubble");
  const panel = new FakeElement("panel", "hidden");
  const dragHandle = new FakeElement("head");
  const reset = new FakeElement("iconbtn");
  const close = new FakeElement("iconbtn");
  const form = new FakeElement("form");
  const input = new FakeElement("input");
  const send = new FakeElement("send");
  const messages = new FakeElement("msgs");
  const lesson = new FakeElement("lesson");

  const shadowElements = new Map([
    ["[data-wrap]", wrap],
    ["[data-bubble]", bubble],
    ["[data-panel]", panel],
    ["[data-drag-handle]", dragHandle],
    ["[data-reset]", reset],
    ["[data-close]", close],
    ["[data-form]", form],
    ["[data-input]", input],
    ["[data-send]", send],
    ["[data-msgs]", messages],
    ["[data-lesson]", lesson],
  ]);
  const shadow = {
    innerHTML: "",
    querySelector(selector) {
      return shadowElements.get(selector) || null;
    },
  };
  const root = new FakeElement();
  root.attachShadow = () => shadow;

  wrap.getBoundingClientRect = () => {
    const isOpen = !panel.classList.contains("hidden");
    const width = isOpen ? 414 : 142;
    const height = isOpen ? 650 : 46;
    const explicitLeft = Number.parseFloat(wrap.style.left);
    const explicitTop = Number.parseFloat(wrap.style.top);
    const left = Number.isFinite(explicitLeft)
      ? explicitLeft
      : viewport.width - width - 20;
    const top = Number.isFinite(explicitTop)
      ? explicitTop
      : viewport.height - height - 20;
    return { left, top, right: left + width, bottom: top + height, width, height };
  };

  const body = new FakeElement();
  const documentElement = {
    clientWidth: viewport.width,
    clientHeight: viewport.height,
    appendChild() {},
  };
  let createdRoot = false;
  const document = {
    body,
    currentScript: {
      getAttribute() {
        return null;
      },
      src: "https://towardsai-tutors-thinkific-tutor-api.hf.space/widget.js",
    },
    documentElement,
    referrer: "",
    title: "Test lesson",
    createElement() {
      if (!createdRoot) {
        createdRoot = true;
        return root;
      }
      return new FakeElement();
    },
    querySelector() {
      return body;
    },
    querySelectorAll() {
      return frames;
    },
  };

  const location = new URL("https://academy.towardsai.net/courses/test/chapters/one/lessons/two");
  const window = {
    CoursePlayerV2: {
      on(name, callback) {
        courseHooks.set(name, callback);
      },
    },
    ResizeObserver: class {
      constructor(callback) {
        resizeObserverCallback = callback;
      }

      observe() {}
    },
    addEventListener(type, listener) {
      if (!windowListeners.has(type)) windowListeners.set(type, []);
      windowListeners.get(type).push(listener);
    },
    clearInterval() {},
    getSelection() {
      return "";
    },
    innerHeight: viewport.height,
    innerWidth: viewport.width,
    localStorage: {
      getItem(key) {
        return storage.get(key) || null;
      },
      setItem(key, value) {
        storage.set(key, value);
      },
    },
    location,
    removeEventListener(type, listener) {
      const listeners = windowListeners.get(type) || [];
      windowListeners.set(
        type,
        listeners.filter((candidate) => candidate !== listener),
      );
    },
    requestAnimationFrame(callback) {
      callback();
      return 1;
    },
    setInterval(callback) {
      callback();
      return 1;
    },
    setTimeout(callback) {
      callback();
      return 1;
    },
  };

  const context = vm.createContext({
    AbortController,
    Event,
    TextDecoder,
    URL,
    console,
    document,
    fetch: async (url, init) => {
      requests.push({ url, body: init?.body ? JSON.parse(init.body) : null });
      return { ok: true, json: async () => ({ eligible: true }) };
    },
    window,
  });
  const widgetSource = await readFile(
    new URL("../static/thinkific-widget.js", import.meta.url),
    "utf8",
  );
  vm.runInContext(widgetSource, context);

  courseHooks.get("hooks:contentDidChange")({
    course: { id: "course-1", title: "Test course" },
    lesson: { id: "lesson-1", title: "Test lesson" },
    user: { id: "student-1" },
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(wrap.classList.contains("hidden"), false);

  function dispatchWindow(type, details) {
    const event = { preventDefault() {}, ...details };
    for (const listener of windowListeners.get(type) || []) listener(event);
  }

  function drag(element, from, to, pointerId = 1) {
    element.dispatch("pointerdown", {
      button: 0,
      clientX: from.x,
      clientY: from.y,
      pointerId,
      pointerType: "mouse",
    });
    dispatchWindow("pointermove", {
      clientX: to.x,
      clientY: to.y,
      pointerId,
    });
    dispatchWindow("pointerup", {
      clientX: to.x,
      clientY: to.y,
      pointerId,
    });
  }

  return {
    bubble,
    close,
    drag,
    dragHandle,
    panel,
    requests,
    rect: () => wrap.getBoundingClientRect(),
    storage,
    triggerResize: () => resizeObserverCallback(),
    wrap,
  };
}


test("minimizing restores the last explicitly moved bubble position", async () => {
  const harness = await createWidgetHarness();
  const initial = harness.rect();
  harness.drag(
    harness.bubble,
    { x: initial.left + 20, y: initial.top + 20 },
    { x: initial.left - 50, y: initial.top - 25 },
  );
  const movedBubble = harness.rect();

  harness.bubble.dispatch("click");
  harness.triggerResize();
  const openPanel = harness.rect();
  assert.ok(openPanel.left < movedBubble.left);
  assert.ok(openPanel.top < movedBubble.top);

  harness.close.dispatch("click");
  const minimizedAgain = harness.rect();
  assert.deepEqual(
    { left: minimizedAgain.left, top: minimizedAgain.top },
    { left: movedBubble.left, top: movedBubble.top },
  );
  assert.equal(
    harness.storage.has("towards-ai-thinkific-tutor-position-v1"),
    false,
  );
  assert.deepEqual(
    JSON.parse(
      harness.storage.get("towards-ai-thinkific-tutor-position-v2"),
    ),
    { left: movedBubble.left, top: movedBubble.top },
  );
});


test("the default bubble returns to the bottom-right after minimizing", async () => {
  const harness = await createWidgetHarness();
  const bottomRight = harness.rect();

  harness.bubble.dispatch("click");
  const openPanel = harness.rect();
  harness.drag(
    harness.dragHandle,
    { x: openPanel.left + 40, y: openPanel.top + 30 },
    { x: 140, y: 120 },
  );
  harness.triggerResize();
  harness.close.dispatch("click");

  const minimizedAgain = harness.rect();
  assert.deepEqual(
    { left: minimizedAgain.left, top: minimizedAgain.top },
    { left: bottomRight.left, top: bottomRight.top },
  );
  assert.equal(harness.wrap.style.left, "");
  assert.equal(harness.wrap.style.top, "");
  assert.equal(harness.wrap.style.right, "");
  assert.equal(harness.wrap.style.bottom, "");
});

test("lesson resolution includes iframe source URLs without reading cross-origin bodies", async () => {
  const url = "https://magnetic-koi.super.site/example-blueprint";
  const harness = await createWidgetHarness({ frames: [{ src: url }] });
  const resolve = harness.requests.find((request) => String(request.url).includes("/api/thinkific/resolve"));
  assert.deepEqual(Array.from(resolve.body.context.extra.lessonContentUrls), [url]);
});
