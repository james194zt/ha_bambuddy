// Injected into Bambuddy's page by the Bambuddy Panel proxy, before the app.
// Bambuddy builds root-relative URLs ("/api/v1/...", "/camera/2") at runtime;
// this sends them through the proxy path instead of Home Assistant's root.
(() => {
  const P = "/api/bambuddy_panel/proxy";
  // Picked up by the router's (rewritten) default basename.
  window.__BB_BASE__ = P;

  const ORIGIN = location.origin;
  const SKIP = /^(data|blob|javascript|mailto|tel|about):/i;
  const inProxy = (path) => path === P || path.startsWith(P + "/");

  const fix = (u) => {
    if (u instanceof URL) u = u.href;
    if (typeof u !== "string" || !u || u[0] === "#" || SKIP.test(u)) return u;
    let url;
    try {
      url = new URL(u, document.baseURI);
    } catch (e) {
      return u;
    }
    if (url.origin !== ORIGIN || inProxy(url.pathname)) return u;
    return ORIGIN + P + url.pathname + url.search + url.hash;
  };

  const fixWs = (u) => {
    let url;
    try {
      url = new URL(String(u), document.baseURI);
    } catch (e) {
      return u;
    }
    if (url.host !== location.host || inProxy(url.pathname)) return u;
    url.pathname = P + url.pathname;
    return url.href;
  };

  const origFetch = window.fetch;
  window.fetch = function (input, init) {
    if (input instanceof Request) {
      const fixed = fix(input.url);
      if (fixed !== input.url) input = new Request(fixed, input);
    } else {
      input = fix(input);
    }
    return origFetch.call(this, input, init);
  };

  const origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    return origOpen.call(this, method, fix(url), ...rest);
  };

  const wrapCtor = (name, fixer) => {
    const Orig = window[name];
    if (!Orig) return;
    window[name] = new Proxy(Orig, {
      construct(target, args) {
        if (args.length) args[0] = fixer(args[0]);
        return Reflect.construct(target, args);
      },
    });
  };
  wrapCtor("WebSocket", fixWs);
  wrapCtor("EventSource", fix);
  wrapCtor("Worker", fix);

  const origWindowOpen = window.open;
  window.open = function (url, ...rest) {
    return origWindowOpen.call(this, url ? fix(url) : url, ...rest);
  };

  const URL_ATTRS = new Set(["src", "href", "poster", "action", "data"]);
  const origSetAttribute = Element.prototype.setAttribute;
  Element.prototype.setAttribute = function (name, value) {
    if (URL_ATTRS.has(String(name).toLowerCase())) value = fix(String(value));
    return origSetAttribute.call(this, name, value);
  };

  for (const [cls, prop] of [
    ["HTMLImageElement", "src"],
    ["HTMLScriptElement", "src"],
    ["HTMLLinkElement", "href"],
    ["HTMLMediaElement", "src"],
    ["HTMLSourceElement", "src"],
    ["HTMLIFrameElement", "src"],
    ["HTMLAnchorElement", "href"],
    ["HTMLFormElement", "action"],
    ["HTMLVideoElement", "poster"],
  ]) {
    const proto = window[cls] && window[cls].prototype;
    const desc = proto && Object.getOwnPropertyDescriptor(proto, prop);
    if (!desc || !desc.set) continue;
    Object.defineProperty(proto, prop, {
      ...desc,
      set(value) {
        desc.set.call(this, fix(value));
      },
    });
  }

  // Full-page navigations (location.href = "/projects") can't be patched
  // directly; where the Navigation API exists, redirect them into the proxy.
  if (window.navigation) {
    window.navigation.addEventListener("navigate", (event) => {
      if (!event.cancelable || event.hashChange) return;
      const url = new URL(event.destination.url);
      if (url.origin !== ORIGIN || inProxy(url.pathname)) return;
      event.preventDefault();
      location.assign(fix(url.href));
    });
  }

  // Bambuddy's service worker would control Home Assistant's whole origin.
  if (navigator.serviceWorker) {
    navigator.serviceWorker.register = () =>
      Promise.reject(new Error("Service worker disabled inside Home Assistant"));
    navigator.serviceWorker.getRegistrations = () => Promise.resolve([]);
    navigator.serviceWorker.getRegistration = () => Promise.resolve(undefined);
  }
})();
