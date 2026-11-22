// SFH Frame Menu — Decky plugin for Steam Frame (hand-written, no build step).
//
// Steam Frame has no Quick Access Menu in VR, so Decky's QAM tab is unreachable.
// This plugin:
//   1. registers the route /sfh-decky that renders Decky's QAM tab content as a page;
//   2. adds a "Decky" item to the Frame left menu (next to Console / Steam Settings).
//
// Two Steam UI builds are handled. The older one is a webpack bundle (window.webpackChunksteamui):
// components are found in its modules and patched where they are defined. The newer one (Steam beta,
// November 2026) is a Vite bundle with no webpack registry; Decky v4 exposes its module scopes
// (DFL.moduleScopes), but plain function components there cannot be replaced at their definition, so
// they are wrapped in the mounted React tree instead (fiber.type), re-checked every 2 s for new mounts.
//
// The Frame left menu is an exported mobx observer (a React.memo object) that maps
// frame.menu.items_for_left_frame_menu. The "steam main menu items" block (Home, Library,
// ..., Console, Settings) is a nested component rendered with the key
// "frame-menu-steam-main-menu-items-N". We wrap the memo's render and swap that block for
// a wrapper that renders the original component and inserts one more route item.

const manifest = { name: "SFH Frame Menu" };
const internals = window.__DECKY_SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED_deckyLoaderAPIInit;
if (!internals) {
  throw new Error("[SFH Frame Menu] Decky loader API is not initialized");
}
const api = internals.connect(2, manifest.name);
const routerHook = api.routerHook;

const React = window.SP_REACT;
const h = React.createElement;

// UI language follows the Steam client language: Russian for "russian", English otherwise.
function steamLanguage() {
  try {
    const loc = window.LocalizationManager?.m_rgLocalesToUse?.[0];
    if (loc) return String(loc);
  } catch (e) {
    // fall through
  }
  return navigator.language || "en";
}
const IS_RU = steamLanguage().toLowerCase().startsWith("ru");
const T = (ru, en) => (IS_RU ? ru : en);
const ROUTE = "/sfh-decky";
const MENU_MARKER = "frame-menu-steam-main-menu-items";
const DECKY_TAB_ID = 999;
const HAS_WEBPACK = !!window.webpackChunksteamui;

// ---------- the Vite build: module scopes, minified names ----------

const IDENT = c => (c >= "a" && c <= "z") || (c >= "A" && c <= "Z") || (c >= "0" && c <= "9") || c === "_" || c === "$";

// The identifier right before `text` in `src` (e.g. "Cm" in "Cm.fromObject("), or null.
function identBefore(src, text) {
  const at = src.indexOf(text);
  if (at <= 0) return null;
  let start = at;
  while (start > 0 && IDENT(src[start - 1])) start--;
  return start < at ? src.slice(start, at) : null;
}

// The digits right after `text` in `src`, as a number, or null.
function numberAfter(src, text) {
  const at = src.indexOf(text);
  if (at < 0) return null;
  let end = at + text.length;
  while (end < src.length && src[end] >= "0" && src[end] <= "9") end++;
  return end > at + text.length ? Number(src.slice(at + text.length, end)) : null;
}

// [scope, value] of the first module-scope variable that passes `test`, or null.
function findScoped(test) {
  if (typeof DFL.findScopeDetailsByVar !== "function") return null;
  const d = DFL.findScopeDetailsByVar(v => {
    try {
      return test(v);
    } catch (e) {
      return false;
    }
  });
  return d ? [d[0], d[1]] : null;
}

// A function component whose source contains every marker.
function findScopedFunction(...markers) {
  const d = findScoped(v => typeof v === "function" && markers.every(m => v.toString().includes(m)));
  return d ? d[1] : null;
}

// Wraps a function component in the mounted tree: every fiber that `match` picks gets
// fiber.type = wrap(fiber.elementType) (one wrapper per component). The wrapper calls the original
// as a plain function, so the original's hooks keep running in the same fiber. Re-checked every
// 2 s for newly mounted copies (menus and popups mount later). Returns the undo function.
function patchMountedFunction(match, wrap) {
  const wrappers = new Map();
  const scan = () => {
    try {
      walkMounted(f => {
        const inner = typeof f.elementType === "function" && match(f) ? f.elementType : null;
        if (!inner) return false;
        let w = wrappers.get(inner);
        if (!w) {
          w = wrap(inner);
          wrappers.set(inner, w);
        }
        if (f.type !== w) f.type = w;
        if (f.alternate && f.alternate.type !== w) f.alternate.type = w;
        return false;
      });
    } catch (e) {
      console.error("[SFH Frame Menu] patch scan failed", e);
    }
  };
  scan();
  const timer = setInterval(scan, 2000);
  return () => {
    clearInterval(timer);
    walkMounted(f => {
      if (f.elementType && wrappers.get(f.elementType) === f.type) {
        f.type = f.elementType;
        if (f.alternate) f.alternate.type = f.elementType;
      }
      return false;
    });
  };
}

function DeckyIcon() {
  return h("svg", { viewBox: "0 0 24 24", width: "1em", height: "1em", fill: "currentColor" },
    h("path", { d: "M7 2h7a8 8 0 0 1 0 16h-1v4H7v-4H4v-4h3V2zm4 4v8h3a4 4 0 0 0 0-8h-3z" }));
}

// ---------- page with Decky's QAM tab ----------

// Decky's PluginView renders a plugin's content only while its QuickAccessVisibleState
// context says the QAM is visible (default: false). tabsHook.render() builds the tab
// exactly as for the QAM, wrapped in that provider, so ask it for a visible tab.
function deckyTab() {
  const hook = window.DeckyPluginLoader?.tabsHook;
  if (!hook) return null;
  const tabs = [];
  hook.render(tabs, true);
  return tabs.find(t => t.key === DECKY_TAB_ID) || null;
}

function DeckyPanel() {
  const tab = React.useMemo(deckyTab, []);
  if (!tab) {
    return h("div", { style: { padding: "32px" } }, T("Decky ещё не загрузился", "Decky has not loaded yet"));
  }
  return h("div", {
    style: { padding: "24px 32px", height: "100%", overflowY: "auto", boxSizing: "border-box" },
  },
    h("div", { style: { fontSize: "26px", fontWeight: "bold", marginBottom: "12px" } }, tab.title),
    tab.panel);
}

// ---------- Frame left menu patch ----------

function findMenuMemo() {
  let req = null;
  window.webpackChunksteamui.push([[Symbol("sfh-frame-menu")], {}, r => { req = r; }]);
  if (!req) return null;
  for (const id of Object.keys(req.m)) {
    if (!req.m[id].toString().includes(MENU_MARKER)) continue;
    const mod = req(id);
    return Object.values(mod).find(v => v && v.$$typeof === Symbol.for("react.memo")) || null;
  }
  return null;
}

function MainItemsWithDecky(props) {
  const { sfhInner: Inner, ...rest } = props;
  const out = Inner(rest);
  try {
    const kids = React.Children.toArray(out?.props?.children ?? []);
    const routeItem = kids.find(k => k?.props?.route);
    if (!routeItem || kids.some(k => String(k.key).includes("sfh-decky"))) return out;
    const decky = h(routeItem.type, {
      key: "sfh-decky",
      route: ROUTE,
      active: "if-within-route",
      label: "Decky",
      icon: h(DeckyIcon),
    });
    const settings = kids.findIndex(k => String(k.key).includes("settings"));
    kids.splice(settings >= 0 ? settings : kids.length, 0, decky);
    return h(React.Fragment, null, ...kids);
  } catch (e) {
    console.error("[SFH Frame Menu] failed to add the Decky item", e);
    return out;
  }
}

// React keeps the render function of an already mounted memo component in its fiber
// (fiber.type), so replacing memo.type only affects new mounts. The Frame menu is
// usually mounted before Decky loads plugins: retarget the mounted fibers as well.
// Popup windows are portals of the SharedJSContext React roots, so walking those
// roots reaches the menu in every Frame window.
function retargetMounted(memo, from, to) {
  for (const el of document.querySelectorAll("*")) {
    const key = Object.keys(el).find(k => k.startsWith("__reactContainer"));
    if (!key) continue;
    const stack = [el[key]];
    while (stack.length) {
      const f = stack.pop();
      if (f.elementType === memo && f.type === from) {
        f.type = to;
        if (f.alternate && f.alternate.type === from) f.alternate.type = to;
      }
      if (f.child) stack.push(f.child);
      if (f.sibling) stack.push(f.sibling);
    }
  }
}

function patchFrameMenu() {
  if (!HAS_WEBPACK) {
    // the main menu items block: the element keyed "frame-menu-steam-main-menu-items-N"
    return patchMountedFunction(
      f => typeof f.key === "string" && f.key.startsWith(MENU_MARKER),
      inner => function SfhMainItems(props) {
        return MainItemsWithDecky({ ...props, sfhInner: inner });
      });
  }
  const memo = findMenuMemo();
  if (!memo) {
    console.warn("[SFH Frame Menu] Frame menu component not found, menu item not added");
    return () => {};
  }
  if (memo.__sfhOrig) return () => {};
  const orig = memo.type;
  memo.__sfhOrig = orig;
  memo.type = function SfhFrameMenu(...args) {
    const res = orig.apply(this, args);
    try {
      const children = res?.props?.children;
      if (!Array.isArray(children)) return res;
      const patched = children.map(c =>
        c && typeof c.key === "string" && c.key.startsWith(MENU_MARKER)
          ? h(MainItemsWithDecky, { ...c.props, sfhInner: c.type, key: c.key })
          : c);
      return React.cloneElement(res, {}, patched);
    } catch (e) {
      console.error("[SFH Frame Menu] menu patch failed", e);
      return res;
    }
  };
  const patched = memo.type;
  try {
    retargetMounted(memo, orig, patched);
  } catch (e) {
    console.error("[SFH Frame Menu] could not retarget the mounted menu", e);
  }
  return () => {
    if (memo.__sfhOrig) {
      memo.type = memo.__sfhOrig;
      delete memo.__sfhOrig;
      try {
        retargetMounted(memo, patched, orig);
      } catch (e) {
        console.error("[SFH Frame Menu] could not restore the mounted menu", e);
      }
    }
  };
}

// ---------- Frame Quick Settings (bar popup) patch ----------
//
// On Steam Frame the quick settings popup is the QuickAccessMenu function (DT) rendered
// directly by the bar's quick-access button: <BarPopup popupContents={<DT vr .../>}>.
// Decky only patches the BrowserView/Embedded memo wrappers around DT, so its tab never
// shows up on Frame. The bar itself is a local React.memo (not exported); we find it in
// the mounted tree by its source, wrap its render, swap the quick-access button for a
// wrapper whose popup content is DT plus Decky's tab — added the same way Decky does it
// on the Deck: tabsHook.render() pushes into DT's props.tabs array.

const QAM_BUTTON_MARKER = "#VRDashboard_QuickAccessMenu";
const BAR_MARKERS = ["SmallBarButtons", "Tray"];

function walkMounted(visit) {
  for (const el of document.querySelectorAll("*")) {
    const key = Object.keys(el).find(k => k.startsWith("__reactContainer"));
    if (!key) continue;
    const stack = [el[key]];
    while (stack.length) {
      const f = stack.pop();
      if (visit(f) === true) return;
      if (f.child) stack.push(f.child);
      if (f.sibling) stack.push(f.sibling);
    }
  }
}

function findBarMemo() {
  let found = null;
  walkMounted(f => {
    const t = f.elementType;
    if (t && t.$$typeof === Symbol.for("react.memo") && typeof t.type === "function") {
      const src = (t.__sfhOrig || t.type).toString();
      if (BAR_MARKERS.every(m => src.includes(m)) && src.includes("ON_FRAME")) {
        found = t;
        return true;
      }
    }
    return false;
  });
  return found;
}

function QamWithDecky(props) {
  const { sfhQam: Qam, ...rest } = props;
  const ret = Qam(rest);
  try {
    const node = DFL.findInReactTree(ret, x => Array.isArray(x?.props?.tabs));
    const hook = window.DeckyPluginLoader?.tabsHook;
    if (node && hook && !node.props.tabs.some(t => t?.decky)) {
      const tabs = node.props.tabs;
      hook.render(tabs, rest.visible !== false);
      // In VR the tab button renders only tabs placed in the quick access menu
      // (vrLocation), and the popup is sized by vrPopupSize: take it from a native tab.
      const native = tabs.find(t => t && !t.decky && t.vrLocation === "quick-access-menu");
      for (const t of tabs) {
        if (!t?.decky) continue;
        t.vrLocation = "quick-access-menu";
        if (native?.vrPopupSize) t.vrPopupSize = native.vrPopupSize;
        t.strTitle = "Decky";
      }
    }
  } catch (e) {
    console.error("[SFH Frame Menu] failed to add the Decky tab", e);
  }
  return ret;
}

function QamButtonWithDecky(props) {
  const { sfhButton: Button, ...rest } = props;
  const ret = Button(rest);
  const popup = ret?.props?.popupContents;
  if (!popup || typeof popup.type !== "function" || popup.type === QamWithDecky) return ret;
  return React.cloneElement(ret, {
    popupContents: h(QamWithDecky, { ...popup.props, sfhQam: popup.type }),
  });
}

function isQamButton(el) {
  return el && typeof el.type === "function" && el.type !== QamButtonWithDecky &&
    el.type.toString().includes(QAM_BUTTON_MARKER);
}

function patchQuickSettings() {
  if (!HAS_WEBPACK) {
    // the bar's quick-access button: renders <BarPopup popupContents={<QuickAccessMenu vr …/>}>
    const button = findScopedFunction(QAM_BUTTON_MARKER, "popupContents");
    if (!button) return null;
    return patchMountedFunction(
      f => f.elementType === button,
      inner => function SfhQamButton(props) {
        return QamButtonWithDecky({ ...props, sfhButton: inner });
      });
  }
  const memo = findBarMemo();
  if (!memo) return null;
  if (memo.__sfhOrig) return () => {};
  const orig = memo.type;
  memo.__sfhOrig = orig;
  memo.type = function SfhFrameBar(...args) {
    const res = orig.apply(this, args);
    try {
      const parent = DFL.findInReactTree(res, n =>
        Array.isArray(n?.props?.children) && n.props.children.some(isQamButton));
      if (parent) {
        parent.props.children = parent.props.children.map(c => isQamButton(c)
          ? h(QamButtonWithDecky, { ...c.props, sfhButton: c.type, key: c.key })
          : c);
      }
    } catch (e) {
      console.error("[SFH Frame Menu] bar patch failed", e);
    }
    return res;
  };
  const patched = memo.type;
  retargetMounted(memo, orig, patched);
  return () => {
    if (memo.__sfhOrig) {
      memo.type = memo.__sfhOrig;
      delete memo.__sfhOrig;
      retargetMounted(memo, patched, orig);
    }
  };
}

// The bar may mount after the plugin loads: retry for a while.
function patchQuickSettingsWithRetry() {
  let unpatch = null;
  let tries = 0;
  const attempt = () => {
    try {
      unpatch = patchQuickSettings();
    } catch (e) {
      console.error("[SFH Frame Menu] quick settings patch error", e);
    }
    if (!unpatch && ++tries < 30) timer = setTimeout(attempt, 2000);
    if (!unpatch && tries >= 30) console.warn("[SFH Frame Menu] Frame bar not found, no Decky tab");
  };
  let timer = setTimeout(attempt, 0);
  return () => {
    clearTimeout(timer);
    unpatch?.();
  };
}

// ---------- Decky's own button on the Frame bar (Decky v4) ----------
//
// Decky v4 puts a "Decky" button on the Frame bar itself: it afterPatches a memo component of the
// bar and adds a forwardRef button with tooltip "Decky". To hide it we wrap that memo's render once
// more (over Decky's patch) and drop the button from what it returns.

function isDeckyBarButton(el) {
  return !!el && typeof el === "object" && el.props?.tooltip === "Decky" && el.type?.$$typeof === Symbol.for("react.forward_ref");
}

// The bar memo that renders Decky's button: the nearest memo above the mounted button.
function findDeckyBarMemo() {
  let found = null;
  walkMounted(f => {
    if (f.memoizedProps?.tooltip !== "Decky" || f.elementType?.$$typeof !== Symbol.for("react.forward_ref")) return false;
    for (let p = f.return; p; p = p.return) {
      if (p.elementType?.$$typeof === Symbol.for("react.memo") && typeof p.elementType.type === "function") {
        found = p.elementType;
        return true;
      }
    }
    return false;
  });
  return found;
}

// Children with Decky's button taken out, at any depth (it sits in a nested array of the bar's
// children: Decky appends [button] to the list).
function stripDeckyButton(kids) {
  if (Array.isArray(kids)) return kids.filter(k => !isDeckyBarButton(k)).map(stripDeckyButton);
  if (kids && typeof kids === "object" && kids.props && "children" in kids.props) {
    kids.props.children = stripDeckyButton(kids.props.children);
  }
  return kids;
}

// The bar is a mobx observer: a patched or restored render shows only when it renders again. Tell
// each mounted copy's mobx reaction that its store changed (what mobx itself does on a change).
function rerenderMounted(memo) {
  walkMounted(f => {
    if (f.elementType !== memo) return false;
    for (let h = f.memoizedState; h; h = h.next) {
      const adm = h.memoizedState?.current;
      if (adm && typeof adm.onStoreChange === "function" && "stateVersion" in adm) {
        adm.stateVersion = Symbol();
        adm.onStoreChange();
        break;
      }
    }
    return false;
  });
}

function hideDeckyBarButton() {
  const memo = findDeckyBarMemo();
  if (!memo) return null;
  if (memo.__sfhBarOrig) return () => {};
  const orig = memo.type;
  memo.__sfhBarOrig = orig;
  memo.type = function SfhBarNoDecky(...args) {
    const res = orig.apply(this, args);
    try {
      if (isDeckyBarButton(res)) return null;
      stripDeckyButton(res);
    } catch (e) {
      console.error("[SFH Frame Menu] could not hide Decky's bar button", e);
    }
    return res;
  };
  const patched = memo.type;
  retargetMounted(memo, orig, patched);
  rerenderMounted(memo);
  return () => {
    if (memo.__sfhBarOrig) {
      if (memo.type === patched) memo.type = memo.__sfhBarOrig;
      delete memo.__sfhBarOrig;
      retargetMounted(memo, patched, orig);
      rerenderMounted(memo);
    }
  };
}

// The bar (and Decky's button on it) mounts only while the dashboard is shown: keep looking every
// 2 s until it is there; once the memo is patched, later mounts use the patched render.
function hideDeckyBarButtonWithRetry() {
  let undo = null, timer = null;
  const attempt = () => {
    try {
      undo = hideDeckyBarButton();
    } catch (e) {
      console.error("[SFH Frame Menu] bar button hide error", e);
    }
    if (!undo) timer = setTimeout(attempt, 2000);
  };
  timer = setTimeout(attempt, 0);
  return () => {
    clearTimeout(timer);
    undo?.();
  };
}

// ---------- VR HUD switch ----------
//
// The SFH VR HUD (tools/vr_hud.py) polls window.__sfhHud in this JS context over CDP
// every 0.25 s: bumping .toggle shows/hides it, and it writes back .visible and .seen
// (Date.now() of its last poll). No backend needed.

function hudState() {
  const s = window.__sfhHud;
  const alive = !!(s && s.seen && Date.now() - s.seen < 3000);
  return { alive, visible: alive && s.visible !== false };
}

function HudPanel() {
  const [state, setState] = React.useState(hudState);
  React.useEffect(() => {
    const timer = setInterval(() => setState(hudState()), 400);
    return () => clearInterval(timer);
  }, []);
  const toggle = () => {
    const s = window.__sfhHud = window.__sfhHud || { toggle: 0 };
    s.toggle = (s.toggle || 0) + 1;
  };
  return h(DFL.PanelSection, { title: T("Статистика соединения", "Connection stats") },
    h(DFL.PanelSectionRow, null,
      h(DFL.ToggleField, {
        label: T("Показывать в шлеме", "Show in headset"),
        description: state.alive
          ? T("Пинг, потери и трафик до ПК внизу поля зрения", "Ping, packet loss and traffic to the PC at the bottom of your view")
          : T("Не запущена: включите в SFH (Инструменты → Сеть)", "Not running: turn it on in SFH (Tools → Network)"),
        checked: state.visible,
        disabled: !state.alive,
        onChange: toggle,
      })));
}

// ---------- turn off the Frame controllers ----------
//
// SteamClient.Input.TurnOffController (the Steam "turn off controller" item / chord
// action) does nothing for Frame controllers. What works is the Frame pairing store's
// DisconnectAllControllers — the same as Settings → Controller → "Disconnect all
// controllers": it powers off both controllers (they come back with the Steam button).

const PAIRING_MARKER = "Disconnect all Frame VR Controllers Sent";

// One controller: the pairing protocol has a disconnect_controller message (by serial
// number) that the Steam UI never sends. We build it with the same protobuf class and
// send it through the same connection the store uses (found in the store's module).
// role values as sent by the pairing service (checked on a Frame): 1 = left, 2 = right
const ROLE_LEFT = 1, ROLE_RIGHT = 2;

// Module ids a webpack module imports: the digits in each "t(<digits>)" of its source.
function importedIds(src) {
  const ids = [];
  let pos = src.indexOf("t(");
  while (pos >= 0) {
    let end = pos + 2;
    while (end < src.length && src[end] >= "0" && src[end] <= "9") end++;
    if (end > pos + 2 && src[end] === ")") ids.push(src.slice(pos + 2, end));
    pos = src.indexOf("t(", pos + 2);
  }
  return ids;
}

function findPairing() {
  if (!HAS_WEBPACK) {
    // DisconnectAllControllers(){let e=<Msg>.fromObject({disconnect_all_controllers:!0});<Conn>.BSendMsg(<id>,e)…}
    // The message, the connection and the message id are read from its source; both names live in
    // the store's module scope.
    const d = findScoped(v => v && typeof v === "object" && typeof v.DisconnectAllControllers === "function");
    if (!d) return null;
    const [scope, store] = d;
    const src = store.DisconnectAllControllers.toString();
    const msgName = identBefore(src, ".fromObject(");
    const connName = identBefore(src, ".BSendMsg(");
    const id = numberAfter(src, ".BSendMsg(");
    const Msg = msgName ? scope[msgName] : null, conn = connName ? scope[connName] : null;
    const ok = Msg && typeof Msg.fromObject === "function" && conn && typeof conn.BSendMsg === "function" && id !== null;
    return { store, sender: ok ? conn : null, proto: ok ? { Msg, id } : null };
  }
  let req = null;
  window.webpackChunksteamui.push([[Symbol("sfh-frame-pairing")], {}, r => { req = r; }]);
  if (!req) return null;
  for (const id of Object.keys(req.m)) {
    const src = req.m[id].toString();
    if (!src.includes(PAIRING_MARKER)) continue;
    const mod = req(id);
    const store = Object.values(mod).find(v => v && typeof v.DisconnectAllControllers === "function");
    if (!store) continue;
    // The store's module imports the sender (…N.BSendMsg) and the protobuf module
    // (…hp, …lK). Only modules it imports (t(<id>) in its source) are candidates, so
    // we use exactly the connection DisconnectAllControllers uses.
    let sender = null, proto = null;
    for (const mid of importedIds(src)) {
      let exp = null;
      try {
        exp = req(mid);
      } catch (e) {
        continue;
      }
      if (!exp) continue;
      if (!proto && exp.hp?.M?.().fields?.disconnect_controller && exp.lK?.Gd !== undefined) proto = exp;
      if (!sender && typeof exp.N?.BSendMsg === "function" && typeof exp.N?.RegisterOnMsg === "function") {
        sender = exp.N;
      }
      if (sender && proto) break;
    }
    return { store, sender, proto };
  }
  return null;
}

function connectedControllers(p) {
  try {
    return p.store.m_controllerPairingState.toObject().connected_controller || [];
  } catch (e) {
    return [];
  }
}

function disconnectOne(p, serial) {
  if (p.proto.Msg) {   // the Vite build
    p.sender.BSendMsg(p.proto.id, p.proto.Msg.fromObject({ disconnect_controller: { serial_number: serial } }));
    return;
  }
  const msg = p.proto.hp.fromObject({ disconnect_controller: { serial_number: serial } });
  p.sender.BSendMsg(p.proto.lK.Gd, msg);
}

// Steam's own Frame controller icon (the one next to each controller's battery level):
// IndividualSteamFrameController({ bIsLeftController }). Fallback: a letter.
// A named icon component from Steam's icon module (e.g. "SteamFrameIcon"), or null.
function findSteamIcon(name) {
  if (!HAS_WEBPACK) return null;   // export names are minified away in the Vite build
  let req = null;
  window.webpackChunksteamui.push([[Symbol("sfh-frame-icon")], {}, r => { req = r; }]);
  if (!req) return null;
  for (const id of Object.keys(req.m)) {
    if (!req.m[id].toString().includes(name)) continue;
    try {
      const icon = req(id)[name];
      if (typeof icon === "function") return icon;
    } catch (e) {
      // not the icon module
    }
  }
  return null;
}

function findControllerIcon() {
  if (!HAS_WEBPACK) {
    // the Frame controllers' battery row draws it: (0,Y.jsx)(<Icon>,{bIsLeftController:!0})
    const d = findScoped(v => typeof v === "function" && v.toString().includes("#Settings_Controller_Battery") &&
      v.toString().includes(",{bIsLeftController"));
    if (!d) return null;
    const name = identBefore(d[1].toString(), ",{bIsLeftController");
    const icon = name ? d[0][name] : null;
    return typeof icon === "function" ? icon : null;
  }
  return findSteamIcon("IndividualSteamFrameController");
}

// Plugin icon in the Decky list: Steam's own Steam Frame headset icon; the "D" logo
// stays as a fallback (and on the "Decky" item in the left menu).
function PluginIcon() {
  const Icon = React.useMemo(() => findSteamIcon("SteamFrameIcon"), []);
  return Icon ? h(Icon, { width: "1em", height: "1em" }) : h(DeckyIcon);
}

// Steam's icon is an SVG without a size of its own (it fills its parent): put it in a
// fixed box and size the svg through a class.
const ICON_SIZE = 22;
const ICON_CSS = `.sfh-ctl-icon{display:inline-flex;width:${ICON_SIZE}px;height:${ICON_SIZE}px;flex:none}` +
  ".sfh-ctl-icon svg{width:100%;height:100%}";

function controllerIcon(Icon, left) {
  const inner = Icon ? h(Icon, { bIsLeftController: left }) : (left ? "L" : "R");
  return h("span", { className: "sfh-ctl-icon" }, inner);
}

// Compact: the height of a regular Decky button row, icons sized to fit it.
const ICON_BUTTON = {
  flex: "1 1 0", minWidth: 0, height: "36px", minHeight: 0, padding: 0,
  fontSize: "16px", lineHeight: 1, overflow: "hidden",
  display: "flex", alignItems: "center", justifyContent: "center", gap: "2px",
};

function ControllersPanel() {
  const p = React.useMemo(findPairing, []);
  const Icon = React.useMemo(findControllerIcon, []);
  const [list, setList] = React.useState(() => (p ? connectedControllers(p) : []));
  React.useEffect(() => {
    const timer = setInterval(() => setList(p ? connectedControllers(p) : []), 1000);
    return () => clearInterval(timer);
  }, [p]);
  if (!p) {
    return h(DFL.PanelSection, { title: T("Выключить контроллеры", "Turn off controllers") },
      h(DFL.PanelSectionRow, null, T("Функция не найдена в этой версии Steam", "Not available in this Steam version")));
  }
  const single = p.sender && p.proto;
  const byRole = role => list.find(c => c.role === role);
  const left = byRole(ROLE_LEFT), right = byRole(ROLE_RIGHT);
  const one = (c, isLeft) => h(DFL.DialogButton, {
    style: ICON_BUTTON,
    disabled: !single || !c,
    onClick: () => c && disconnectOne(p, c.serial_number),
  }, controllerIcon(Icon, isLeft));
  return h(DFL.PanelSection, { title: T("Выключить контроллеры", "Turn off controllers") },
    h("style", null, ICON_CSS),
    h(DFL.PanelSectionRow, null,
      h(DFL.Focusable, {
        "flow-children": "horizontal",
        style: { display: "flex", gap: "6px" },
      },
        one(left, true),
        h(DFL.DialogButton, {
          style: ICON_BUTTON,
          disabled: list.length === 0,
          onClick: () => p.store.DisconnectAllControllers(),
        }, controllerIcon(Icon, true), controllerIcon(Icon, false)),
        one(right, false))));
}

// ---------- where Decky is shown ----------
//
// The user picks where the Decky entry appears: the Frame left menu, the Quick Settings
// popup, or both. Stored in Steam's localStorage (survives restarts) and applied at
// once; Steam redraws the menu / popup the next time it opens. Steam Frame Helper sets
// it through window.__sfhPlacement (tools/decky_placement.py, over CDP).

const PLACEMENT_KEY = "sfh-frame-menu.placement";

function loadPlacement() {
  try {
    const v = JSON.parse(localStorage.getItem(PLACEMENT_KEY) || "{}");
    return { menu: v.menu !== false, qam: v.qam !== false, bar: v.bar !== false };
  } catch (e) {
    return { menu: true, qam: true, bar: true };
  }
}

const placement = {
  value: loadPlacement(),
  unpatchMenu: null,
  unpatchQam: null,
  unhideBar: null,
  listeners: new Set(),

  apply() {
    if (this.value.menu && !this.unpatchMenu) this.unpatchMenu = patchFrameMenu();
    if (!this.value.menu && this.unpatchMenu) { this.unpatchMenu(); this.unpatchMenu = null; }
    if (this.value.qam && !this.unpatchQam) this.unpatchQam = patchQuickSettingsWithRetry();
    if (!this.value.qam && this.unpatchQam) { this.unpatchQam(); this.unpatchQam = null; }
    if (!this.value.bar && !this.unhideBar) this.unhideBar = hideDeckyBarButtonWithRetry();
    if (this.value.bar && this.unhideBar) { this.unhideBar(); this.unhideBar = null; }
  },
  set(next) {
    this.value = { menu: next.menu !== false, qam: next.qam !== false, bar: next.bar !== false };
    try {
      localStorage.setItem(PLACEMENT_KEY, JSON.stringify(this.value));
    } catch (e) {
      console.error("[SFH Frame Menu] could not save placement", e);
    }
    this.apply();
    this.listeners.forEach(fn => fn(this.value));
    return this.value;
  },
  removeAll() {
    this.unpatchQam?.();
    this.unpatchMenu?.();
    this.unhideBar?.();
    this.unpatchQam = this.unpatchMenu = this.unhideBar = null;
  },
};

function PlacementPanel() {
  const [value, setValue] = React.useState(placement.value);
  React.useEffect(() => {
    placement.listeners.add(setValue);
    return () => placement.listeners.delete(setValue);
  }, []);
  // Both may be off: Decky is then opened only from Steam Frame Helper ("Open in headset").
  const row = (key, label, description) => h(DFL.PanelSectionRow, null,
    h(DFL.ToggleField, {
      label,
      description,
      checked: value[key],
      onChange: checked => placement.set({ ...value, [key]: checked }),
    }));
  return h(DFL.PanelSection, { title: T("Где показывать Decky", "Where to show Decky") },
    row("menu", T("Левое меню", "Left menu"),
      T("Пункт «Decky» в меню слева, рядом с настройками",
        "A “Decky” item in the menu on the left, next to Settings")),
    row("qam", T("Быстрые настройки", "Quick Settings"),
      T("Вкладка Decky в окне быстрых настроек на панели",
        "A Decky tab in the Quick Settings popup on the bar")),
    row("bar", T("Кнопка на панели", "Bar button"),
      T("Кнопка «Decky» на нижней панели (её добавляет сам Decky)",
        "The “Decky” button on the bottom bar (added by Decky itself)")),
    h(DFL.PanelSectionRow, null,
      h("div", { style: { fontSize: "12px", opacity: 0.6 } },
        T("Меню обновится при следующем открытии. Если выключить оба, Decky открывается только из Steam Frame Helper (кнопка «Открыть в шлеме»).",
          "The menu updates the next time it opens. With both off, Decky opens only from Steam Frame Helper (the “Open in headset” button)."))));
}

// ---------- plugin ----------

export default DFL.definePlugin(() => {
  // decky_open.py checks this flag so it does not register a second route.
  routerHook.addRoute(ROUTE, DeckyPanel, { exact: true });
  window.__sfhDeckyRoute = true;
  window.__sfhPlacement = {
    get: () => placement.value,
    set: next => placement.set(next),
  };
  placement.apply();

  return {
    name: manifest.name,
    titleView: h("div", null, "SFH Frame Menu"),
    content: h("div", null,
      h(HudPanel),
      h(ControllersPanel),
      h(PlacementPanel)),
    icon: h(PluginIcon),
    onDismount() {
      placement.removeAll();
      delete window.__sfhPlacement;
      routerHook.removeRoute(ROUTE);
      window.__sfhDeckyRoute = false;
    },
  };
});
