// Sidebar panel: gets a proxy session cookie from Home Assistant, then shows
// Bambuddy (served through Home Assistant) in a full-size iframe.
const SESSION_API = "bambuddy_panel/session";
const REFRESH_MS = 30 * 60 * 1000;
const MENU_ICON = "M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z";

class BambuddyPanel extends HTMLElement {
  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = `
      <style>
        /* HA's panel container has no height of its own, only safe-area
           padding, so size to the viewport minus that padding. */
        :host {
          display: flex; flex-direction: column;
          height: calc(100vh - var(--safe-area-inset-top, 0px) - var(--safe-area-inset-bottom, 0px));
          height: calc(100dvh - var(--safe-area-inset-top, 0px) - var(--safe-area-inset-bottom, 0px));
        }
        /* Same header as HA's add-on (ingress) panels, e.g. AdGuard: only
           shown when the sidebar can't be seen. */
        .toolbar {
          display: none; align-items: center; box-sizing: border-box;
          height: 40px; padding: 0 16px; flex: none;
          font-size: var(--ha-font-size-l, 20px);
          font-weight: var(--ha-font-weight-normal, 400);
          background-color: var(--app-header-background-color);
          color: var(--app-header-text-color, white);
          border-bottom: var(--app-header-border-bottom, none);
        }
        :host([show-header]) .toolbar { display: flex; }
        .title { margin-inline-start: var(--ha-space-2, 8px); flex-grow: 1; }
        button {
          background: none; border: 0; color: inherit; padding: 10px;
          margin-inline-start: -10px; cursor: pointer; display: flex;
          border-radius: 50%;
        }
        svg { width: 20px; height: 20px; fill: currentColor; }
        iframe { flex: 1; width: 100%; border: 0; display: block; }
        .error { padding: 24px; color: var(--error-color, #db4437); }
      </style>
      <div class="toolbar">
        <button title="Menu"><svg viewBox="0 0 24 24"><path d="${MENU_ICON}"></path></svg></button>
        <span class="title"></span>
      </div>`;
    root.querySelector("button").addEventListener("click", () =>
      this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true }))
    );
    this._onVisible = () => {
      if (document.visibilityState === "visible") this._refresh();
    };
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    this._updateHeader();
    if (first) this._load();
  }

  set narrow(narrow) {
    this._narrow = !!narrow;
    this._updateHeader();
  }

  _updateHeader() {
    const hidden = this._hass && this._hass.dockedSidebar === "always_hidden";
    this.toggleAttribute("show-header", this._narrow || !!hidden);
  }

  set panel(panel) {
    this.shadowRoot.querySelector(".title").textContent = panel.title || "Bambuddy";
  }

  connectedCallback() {
    this._timer = setInterval(() => this._refresh(), REFRESH_MS);
    document.addEventListener("visibilitychange", this._onVisible);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    document.removeEventListener("visibilitychange", this._onVisible);
  }

  async _load() {
    try {
      const { url } = await this._hass.callApi("POST", SESSION_API);
      const frame = document.createElement("iframe");
      frame.allow = "fullscreen; clipboard-read; clipboard-write";
      frame.src = url;
      this.shadowRoot.appendChild(frame);
    } catch (err) {
      const div = document.createElement("div");
      div.className = "error";
      div.textContent = `Couldn't open Bambuddy: ${err && (err.body?.message || err.message || err.error || err)}`;
      this.shadowRoot.appendChild(div);
    }
  }

  // Keeps the session cookie fresh while the panel stays open.
  _refresh() {
    if (this._hass) this._hass.callApi("POST", SESSION_API).catch(() => {});
  }
}

if (!customElements.get("bambuddy-panel")) {
  customElements.define("bambuddy-panel", BambuddyPanel);
}
