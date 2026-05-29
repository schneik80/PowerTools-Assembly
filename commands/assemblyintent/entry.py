# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

# PowerTools Assembly - New Assembly Intent dialog.
#
# When the user creates a new, empty Fusion Design with Assembly intent, this
# add-in pops up a docked palette offering three quick-start sections:
#
#   1. Create  — make a new external Part/Hybrid component in place, or jump
#                to the Assembly Builder or Global Parameters commands.
#   2. Insert Open    — gallery of currently-open Part/Hybrid/Assembly docs
#                       (saved only, since addByInsert needs a DataFile).
#                       Click a card to insert that doc into the active design.
#   3. Insert Recent  — gallery of recently-touched docs that are NOT currently
#                       open. Backed by a small JSON cache that grows as the
#                       user works.

import base64
import hashlib
import json
import os
import tempfile

import adsk.core
import adsk.fusion

from ... import config
from ...lib import fusionAddInUtils as futil
from ...lib.fusionAddInUtils import cache_utils as cache

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "New Assembly"
PALETTE_NAME = "New Assembly"
PALETTE_ID = config.assembly_intent_palette_id
PALETTE_DOCKING = adsk.core.PaletteDockingStates.PaletteDockStateRight

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")
_HTML_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "resources", "html"
)
PALETTE_URL = os.path.join(_HTML_DIR, "index.html").replace("\\", "/")
INIT_JS_PATH = os.path.join(_HTML_DIR, "init.js")

# Cache file tracking recently-touched part/hybrid/assembly docs.
_RECENT_CACHE_PATH = os.path.join(cache.CACHE_FOLDER, "recent_docs.json")
# Thumbnails go to the OS temp dir — the addin cache folder sometimes lives
# inside the bundled add-in path and can be read-only on locked-down installs.
_THUMB_DIR = os.path.join(tempfile.gettempdir(), "powertools_assembly_thumbs")
_THUMB_SIZE = 86  # ~33% smaller than the previous 128px source.
_RECENT_LIMIT = 24

# Commands we hand off to from the palette.
_ASSEMBLY_BUILDER_CMD_ID = "PTAT-AssemblyBuilder"
_GLOBAL_PARAMETERS_CMD_ID = "PTAT-globalParameters"

# Toolbar button that manually launches the palette. Lives in the Assembly
# Insert panel, directly below the Insert STEP command. The palette also pops
# automatically on new empty Assembly docs (see the documentActivated trigger);
# this button is the on-demand entry point.
LAUNCH_CMD_ID = "PTAT-newAssembly"
LAUNCH_CMD_NAME = "New Assembly"
LAUNCH_CMD_DESC = "Open the New Assembly quick-start palette."
LAUNCH_WORKSPACE_ID = "FusionSolidEnvironment"
LAUNCH_TAB_ID = "AssemblyTab"
LAUNCH_TAB_NAME = "ASSEMBLY"
LAUNCH_PANEL_ID = "InsertAssemblePanel"
LAUNCH_PANEL_NAME = "INSERT"
# Position the control immediately after (below) the Insert STEP command.
LAUNCH_POSITION_REF = "PTAT-insertSTEP"

local_handlers = []


def _diag(msg: str) -> None:
    """Diagnostic log for the document-trigger logic, gated by config.DEBUG so
    release builds stay quiet. When DEBUG is on it writes to the Fusion Text
    Commands window with a clear prefix so it's easy to grep."""
    if not config.DEBUG:
        return
    try:
        app.log(f"[New Assembly] {msg}", adsk.core.LogLevels.InfoLogLevel,
                adsk.core.LogTypes.ConsoleLogType)
    except Exception:
        pass

# Data-file ids inserted from the palette during this palette-open session.
# Cleared on every _show_palette() so a fresh palette open starts clean.
# Without this filter, an inserted-from-Recent doc shows back up in the next
# refresh (it's not "open" in a tab, so Recent re-includes it) and clicking
# again would silently insert a second occurrence into the assembly.
_inserted_in_session: set[str] = set()

# Open-tab filter, toggled from the palette checkbox. Default False → show only
# top-level (directly-opened) docs. True → also include reference-loaded
# children of open assemblies. Both paths are cheap: the top-level test is an
# instant in-memory API check (see _is_top_level_doc), no cloud lookup.
# Persists across palette opens this session.
_show_children = False

# The Document we last popped the palette for (or had open when palette closed).
# Compared via Python identity (`is`) — NOT id(), which can collide across
# short-lived Fusion Document wrappers and previously caused the popup to be
# suppressed after closing + creating a new doc. None means "next eligible
# document activation will pop the palette".
_palette_was_open_for = None


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def start():
    # documentActivated is the reliable trigger across Fusion builds —
    # documentOpened isn't always emitted for File > New on macOS.
    # documentActivated fires on every tab switch too, so we gate manually
    # via _palette_was_open_for (set on show and on close).
    futil.add_handler(app.documentActivated, _on_document_activated)

    # Attach documentOpened as a belt-and-suspenders backup IF this build
    # exposes it. Harmless if it never fires; the gate handles dedup.
    opened_event = getattr(app, "documentOpened", None)
    if opened_event is not None:
        try:
            futil.add_handler(opened_event, _on_document_opened)
            _diag("documentOpened handler attached (backup trigger).")
        except Exception as e:
            _diag(f"documentOpened attach failed: {e}")

    # Manual launch button in the Assembly Insert panel, below Insert STEP.
    cmd_def = ui.commandDefinitions.itemById(LAUNCH_CMD_ID)
    if cmd_def is None:
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            LAUNCH_CMD_ID, LAUNCH_CMD_NAME, LAUNCH_CMD_DESC, ICON_FOLDER
        )
    futil.add_handler(cmd_def.commandCreated, _launch_command_created)

    workspace = ui.workspaces.itemById(LAUNCH_WORKSPACE_ID)
    if workspace is not None:
        toolbar_tab = workspace.toolbarTabs.itemById(LAUNCH_TAB_ID)
        if toolbar_tab is None:
            toolbar_tab = workspace.toolbarTabs.add(LAUNCH_TAB_ID, LAUNCH_TAB_NAME)
        panel = toolbar_tab.toolbarPanels.itemById(LAUNCH_PANEL_ID)
        if panel is None:
            panel = toolbar_tab.toolbarPanels.add(LAUNCH_PANEL_ID, LAUNCH_PANEL_NAME)
        control = panel.controls.addCommand(cmd_def, LAUNCH_POSITION_REF, False)
        control.isPromoted = False

    _diag(f"start(): primary trigger=documentActivated. thumb dir = {_THUMB_DIR}")


def _launch_command_created(args: adsk.core.CommandCreatedEventArgs):
    """Toolbar button clicked — open the palette regardless of the active doc.
    _show_palette() rebuilds a fresh palette each time, so this is safe to
    invoke even when the palette was previously auto-popped and closed."""
    try:
        _show_palette()
    except Exception:
        futil.handle_error(CMD_NAME)


def stop():
    global _palette_was_open_for
    palette = ui.palettes.itemById(PALETTE_ID)
    if palette:
        try:
            palette.deleteMe()
        except Exception:
            pass

    # Remove the launch button. Leave the shared Insert panel/tab in place —
    # insertSTEP owns the conditional panel/tab cleanup.
    workspace = ui.workspaces.itemById(LAUNCH_WORKSPACE_ID)
    if workspace is not None:
        toolbar_tab = workspace.toolbarTabs.itemById(LAUNCH_TAB_ID)
        if toolbar_tab is not None:
            panel = toolbar_tab.toolbarPanels.itemById(LAUNCH_PANEL_ID)
            if panel is not None:
                control = panel.controls.itemById(LAUNCH_CMD_ID)
                if control:
                    control.deleteMe()
    cmd_def = ui.commandDefinitions.itemById(LAUNCH_CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()

    _inserted_in_session.clear()
    _palette_was_open_for = None


# ---------------------------------------------------------------------------
# Trigger
# ---------------------------------------------------------------------------


def _design_is_empty(design: adsk.fusion.Design) -> bool:
    root = design.rootComponent
    if root.occurrences.count > 0:
        return False
    if root.bRepBodies.count > 0:
        return False
    if root.sketches.count > 0:
        return False
    try:
        if design.designType == adsk.fusion.DesignTypes.ParametricDesignType:
            if design.timeline.count > 0:
                return False
    except Exception:
        pass
    return True


def _design_intent(doc: adsk.core.Document) -> int | None:
    try:
        product = doc.products.itemByProductType("DesignProductType")
        design = adsk.fusion.Design.cast(product)
        if design is None:
            return None
        return design.designIntent
    except Exception:
        return None


def _intent_name(intent: int | None) -> str:
    if intent == adsk.fusion.DesignIntentTypes.PartDesignIntentType:
        return "part"
    if intent == adsk.fusion.DesignIntentTypes.HybridDesignIntentType:
        return "hybrid"
    if intent == adsk.fusion.DesignIntentTypes.AssemblyDesignIntentType:
        return "assembly"
    return ""


def _maybe_show_palette_for(doc, source: str) -> None:
    """Shared trigger logic for both document events.

    Eligibility: doc is unsaved + empty Design + Assembly intent.
    Dedup: skip when *doc* is the same Python object we last popped/closed
    against. The dedup uses `is` (object identity), not id(), since id() of
    Fusion's Document wrappers can collide once a wrapper is GC'd.
    """
    global _palette_was_open_for

    if doc is None:
        _diag(f"{source}: doc is None — skip.")
        return

    if doc.isSaved:
        _remember_recent_if_eligible(doc)
        return

    try:
        product = doc.products.itemByProductType("DesignProductType")
    except Exception as e:
        _diag(f"{source}: products access raised: {e}")
        return
    design = adsk.fusion.Design.cast(product)
    if design is None:
        _diag(f"{source}: '{doc.name}' has no Design product — skip.")
        return

    if design.designIntent != adsk.fusion.DesignIntentTypes.AssemblyDesignIntentType:
        _diag(f"{source}: '{doc.name}' intent != Assembly — skip.")
        return
    if not _design_is_empty(design):
        _diag(f"{source}: '{doc.name}' not empty — skip.")
        return

    if _palette_was_open_for is doc:
        _diag(f"{source}: already showed palette for '{doc.name}' — skip.")
        return

    _diag(f"{source}: opening palette for new empty Assembly '{doc.name}'.")
    _palette_was_open_for = doc
    _show_palette()


def _on_document_activated(args: adsk.core.DocumentEventArgs):
    """Primary trigger. Fires on every tab switch, but the dedup gate in
    _maybe_show_palette_for keeps the popup from re-firing for the same doc."""
    try:
        _maybe_show_palette_for(args.document, "documentActivated")
    except Exception:
        futil.handle_error(CMD_NAME)


def _on_document_opened(args: adsk.core.DocumentEventArgs):
    """Backup trigger. Some Fusion builds emit this for File > New; others
    don't. The same dedup gate handles overlap with documentActivated."""
    try:
        _maybe_show_palette_for(args.document, "documentOpened")
    except Exception:
        futil.handle_error(CMD_NAME)


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------


def _show_palette():
    # Fresh palette open → forget which docs were inserted during a prior open
    # so the user can deliberately insert them again in this new session.
    _inserted_in_session.clear()

    palettes = ui.palettes
    palette = palettes.itemById(PALETTE_ID)

    # Fusion's palette.closed sometimes leaves a palette object in
    # `ui.palettes` that has been internally torn down — toggling isVisible
    # on it silently no-ops. The reliable cure is to delete any pre-existing
    # palette and create a fresh one. That also means we re-register
    # navigation / incoming / closed handlers cleanly each time, avoiding
    # accumulating stale handlers across sessions.
    if palette is not None:
        try:
            palette.deleteMe()
        except Exception as e:
            _diag(f"could not deleteMe() existing palette: {e}")
        palette = None

    _write_init_js(_gather_palette_state())
    palette = palettes.add(
        id=PALETTE_ID,
        name=PALETTE_NAME,
        htmlFileURL=PALETTE_URL,
        isVisible=True,
        showCloseButton=True,
        isResizable=True,
        width=420,
        height=720,
        useNewWebBrowser=True,
    )
    futil.add_handler(palette.closed, _palette_closed)
    futil.add_handler(palette.navigatingURL, _palette_navigating)
    futil.add_handler(palette.incomingFromHTML, _palette_incoming)

    if palette.dockingState == adsk.core.PaletteDockingStates.PaletteDockStateFloating:
        palette.dockingState = PALETTE_DOCKING

    palette.isVisible = True


def _gather_palette_state() -> dict:
    doc = app.activeDocument
    return {
        "docName": getattr(doc, "name", ""),
        "theme": _theme_str(),
        "showChildren": _show_children,
        "openDocs": _list_open_docs(),
        "recentDocs": _list_recent_docs(),
    }


def _theme_str() -> str:
    themes = adsk.core.UserInterfaceThemes
    theme = app.preferences.generalPreferences.userInterfaceTheme
    if theme == themes.DeviceUserInterfaceTheme:
        return "dark" if _os_is_dark() else "light"
    if theme in (
        themes.DarkBlueUserInterfaceTheme,
        themes.DarkGrayUserInterfaceTheme,
    ):
        return "dark"
    return "light"


def _os_is_dark() -> bool:
    import sys

    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return val == 0
        except Exception:
            return True
    if sys.platform == "darwin":
        try:
            import subprocess

            out = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            return out.stdout.strip() == "Dark"
        except Exception:
            return True
    return True


def _write_init_js(state: dict) -> None:
    try:
        payload = json.dumps(state)
        with open(INIT_JS_PATH, "w", encoding="utf-8") as fh:
            fh.write(f"window.__ptInit = {payload};\n")
    except Exception as e:
        futil.log(f"{CMD_NAME}: could not write init.js — {e}")


def _send_palette_init(palette: adsk.core.Palette):
    state = _gather_palette_state()
    palette.sendInfoToHTML("setDocumentName", state["docName"])
    palette.sendInfoToHTML("setTheme", state["theme"])
    palette.sendInfoToHTML("setOpenDocs", json.dumps(state["openDocs"]))
    palette.sendInfoToHTML("setRecentDocs", json.dumps(state["recentDocs"]))


def _palette_closed(args: adsk.core.UserInterfaceGeneralEventArgs):
    """Tear the palette down completely on close so the next show() builds a
    fresh one with fresh handlers. Without deleteMe() here, a stale palette
    object lingered in ui.palettes after close and the next show() silently
    no-op'd on isVisible — leaving the user with no palette.

    We also pin *_palette_was_open_for* to the currently-active document so
    that any spurious documentActivated event Fusion fires immediately after
    close (e.g. when CEF releases focus) doesn't immediately re-pop the
    palette for the same doc. Creating a NEW doc will produce a different
    Document instance which trips the `is` check and pops normally."""
    global _palette_was_open_for
    _diag("palette closed — tearing down.")
    _inserted_in_session.clear()
    try:
        _palette_was_open_for = app.activeDocument
    except Exception:
        _palette_was_open_for = None
    palette = ui.palettes.itemById(PALETTE_ID)
    if palette is not None:
        try:
            palette.deleteMe()
        except Exception as e:
            _diag(f"deleteMe() in close handler raised: {e}")


def _palette_navigating(args: adsk.core.NavigationEventArgs):
    url = args.navigationURL
    if url.startswith("http"):
        args.launchExternally = True


# ---------------------------------------------------------------------------
# Open / recent document enumeration
# ---------------------------------------------------------------------------


def _is_top_level_doc(doc) -> bool:
    """True for a document the user opened directly (a tab), False for one
    loaded only as a reference (a sub-assembly/part of an open assembly).

    Fusion exposes this directly and instantly: Document.documentReferences
    raises "Cannot get documentReferences of a non-top-level document" for a
    reference-loaded child, and returns the reference collection for a
    top-level doc. No cloud round-trip, unlike DataFile.childReferences."""
    try:
        # Touch .count so the accessor actually evaluates and raises for
        # non-top-level docs rather than handing back a lazy wrapper.
        doc.documentReferences.count
        return True
    except Exception:
        return False


def _list_open_docs() -> list[dict]:
    """Open Fusion design docs (part/hybrid/assembly) for the Open tab.

    By default only top-level (directly-opened) docs appear; when
    _show_children is set, reference-loaded children of open assemblies are
    included too. Always excludes the active doc, unsaved docs (addByInsert
    needs a DataFile), and docs inserted earlier in this palette session."""
    out: list[dict] = []
    active = app.activeDocument
    active_key = id(active) if active else None

    # Dedup by DataFile id so a doc that's open in more than one document
    # wrapper (or otherwise enumerated twice) only yields a single card —
    # mirrors the `seen` guard in _list_recent_docs.
    seen: set[str] = set()

    for i in range(app.documents.count):
        try:
            doc = app.documents.item(i)
        except Exception:
            continue
        if doc is None:
            continue
        if id(doc) == active_key:
            continue
        if not doc.isSaved:
            continue
        if not _show_children and not _is_top_level_doc(doc):
            continue
        intent = _design_intent(doc)
        intent_name = _intent_name(intent)
        if intent_name not in ("part", "hybrid", "assembly"):
            continue
        try:
            df = doc.dataFile
        except Exception:
            df = None
        if df is None:
            continue
        df_id = getattr(df, "id", "")
        if df_id in _inserted_in_session:
            continue
        if df_id in seen:
            continue
        seen.add(df_id)
        out.append(
            {
                "dataFileId": df_id,
                "name": getattr(df, "name", "") or doc.name,
                "intent": intent_name,
                "thumbUrl": _thumbnail_for_open_doc(doc, df_id),
            }
        )
    return out


def _thumb_path_for(df_id: str) -> str:
    safe = hashlib.md5(df_id.encode("utf-8")).hexdigest()
    return os.path.join(_THUMB_DIR, f"{safe}.png")


def _png_to_data_url(path: str) -> str:
    try:
        with open(path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return ""


_API_INTROSPECTED = False


def _introspect_data_object(data_object) -> None:
    """Dump (once) the DataObject API surface so we know how to extract bytes
    if saveAsFile isn't there."""
    global _API_INTROSPECTED
    if _API_INTROSPECTED:
        return
    _API_INTROSPECTED = True
    try:
        attrs = [n for n in dir(data_object) if not n.startswith("_")]
        _diag(f"DataObject API surface: {attrs}")
    except Exception as e:
        _diag(f"introspect raised: {e}")


def _call_create_thumbnail(root, cache_path: str, name: str) -> str:
    """Call Component.createThumbnail(width, height, imageType="PNG") and
    persist the returned DataObject to *cache_path* via its saveAsFile
    method. Returns the on-disk path on success, "" on failure.

    The Fusion docs:
      returnValue = component_var.createThumbnail(width, height, imageType)
      imageType is a string: "PNG" / "JPG" / "TIF" / "BMP"
      returnValue is a DataObject; use .saveAsFile(...) or read its bytes.
    """
    if not hasattr(root, "createThumbnail"):
        _diag("Component has no createThumbnail attribute on this build.")
        return ""

    try:
        data_object = root.createThumbnail(_THUMB_SIZE, _THUMB_SIZE, "PNG")
    except Exception as e:
        _diag(f"'{name}' createThumbnail raised: {e}")
        return ""

    if data_object is None:
        _diag(f"'{name}' createThumbnail returned None.")
        return ""

    saver = getattr(data_object, "saveToFile", None)
    if callable(saver):
        try:
            ok = saver(cache_path)
        except Exception as e:
            _diag(f"'{name}' DataObject.saveToFile raised: {e}")
            ok = False
        if ok and os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
            return cache_path
        _diag(f"'{name}' saveToFile returned {ok!r}; falling back to base64.")

    # Fallback: pull base64 PNG bytes from the DataObject and write them
    # ourselves. This works on every DataObject and avoids any path-handling
    # quirks in saveToFile.
    b64_getter = getattr(data_object, "getAsBase64String", None)
    if callable(b64_getter):
        try:
            b64 = b64_getter()
        except Exception as e:
            _diag(f"'{name}' getAsBase64String raised: {e}")
            return ""
        if not b64:
            _diag(f"'{name}' getAsBase64String returned empty.")
            return ""
        try:
            png_bytes = base64.b64decode(b64)
            with open(cache_path, "wb") as fh:
                fh.write(png_bytes)
        except Exception as e:
            _diag(f"'{name}' base64 decode/write failed: {e}")
            return ""
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
            return cache_path

    _introspect_data_object(data_object)
    _diag(f"'{name}' could not persist DataObject — see API dump.")
    return ""


def _thumbnail_for_open_doc(doc, df_id: str) -> str:
    """Render *doc*'s root component to a PNG via Component.createThumbnail,
    cache it under df_id, and return a data: URL.

    Why createThumbnail and not DataFile.thumbnail: in this Fusion build the
    DataFile-backed cloud thumbnail never resolved (silent failure). Rendering
    the live component from the in-memory design is reliable so long as the
    document is open — which it is, since this is only called from the Open
    gallery path.
    """
    name = getattr(doc, "name", df_id)

    cache_path = _thumb_path_for(df_id) if df_id else ""
    if cache_path and os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        return _png_to_data_url(cache_path)

    if not cache_path:
        _diag(f"'{name}' no df_id — cannot cache thumbnail.")
        return ""

    try:
        os.makedirs(_THUMB_DIR, exist_ok=True)
    except Exception as e:
        _diag(f"thumb dir create failed ({_THUMB_DIR}): {e}")
        return ""

    try:
        product = doc.products.itemByProductType("DesignProductType")
        design = adsk.fusion.Design.cast(product)
    except Exception as e:
        _diag(f"'{name}' design access raised: {e}")
        return ""
    if design is None:
        _diag(f"'{name}' has no Design product.")
        return ""

    produced = _call_create_thumbnail(design.rootComponent, cache_path, name)
    if not produced:
        return ""

    _diag(
        f"'{name}' cached → {cache_path} "
        f"({os.path.getsize(cache_path)} bytes)"
    )
    return _png_to_data_url(cache_path)


def _cached_thumbnail(df_id: str) -> str:
    """Return a cached PNG (if present on disk from a prior open-doc render)
    as a data: URL, else empty. Used for Recent — closed docs cannot be
    rendered via Component.createThumbnail since there is no live design."""
    if not df_id:
        return ""
    path = _thumb_path_for(df_id)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return _png_to_data_url(path)
    return ""


def _find_data_file_by_id(df_id: str):
    """Best-effort DataFile resolution from an id. Returns None on failure."""
    if not df_id:
        return None
    for owner in (app.data.activeProject, app.data):
        finder = getattr(owner, "findFileById", None)
        if callable(finder):
            try:
                df = finder(df_id)
                if df is not None:
                    return df
            except Exception:
                pass
    return None


def _read_recent_cache() -> list[dict]:
    if not os.path.exists(_RECENT_CACHE_PATH):
        return []
    try:
        with open(_RECENT_CACHE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return data
    except Exception:
        futil.log(f"{CMD_NAME}: recent cache unreadable — starting fresh.")
    return []


def _write_recent_cache(entries: list[dict]) -> None:
    try:
        os.makedirs(os.path.dirname(_RECENT_CACHE_PATH), exist_ok=True)
        with open(_RECENT_CACHE_PATH, "w", encoding="utf-8") as fh:
            json.dump(entries[-_RECENT_LIMIT:], fh, indent=2)
    except Exception as e:
        futil.log(f"{CMD_NAME}: could not write recent cache — {e}")


def _touch_recent(df_id: str, name: str, intent_name: str) -> None:
    """Append (or move to end) a recent entry. Thumbnails are cached on disk
    separately and derived from df_id at list time, so the JSON cache stays
    small."""
    try:
        if not df_id:
            return
        entries = _read_recent_cache()
        entries = [e for e in entries if e.get("dataFileId") != df_id]
        entries.append(
            {"dataFileId": df_id, "name": name or "", "intent": intent_name}
        )
        _write_recent_cache(entries)
    except Exception as e:
        futil.log(f"{CMD_NAME}: _touch_recent failed — {e}")


def _remember_recent_if_eligible(doc: adsk.core.Document | None) -> None:
    """Record *doc* in the recent cache when it's a saved part/hybrid/assembly,
    and pre-warm its thumbnail cache while the doc is open (the only time
    Component.createThumbnail can run on it). Called from documentActivated so
    both grow as the user works."""
    try:
        if doc is None or not doc.isSaved:
            return
        intent_name = _intent_name(_design_intent(doc))
        if intent_name not in ("part", "hybrid", "assembly"):
            return
        df = getattr(doc, "dataFile", None)
        if df is None:
            return
        df_id = getattr(df, "id", "")
        _touch_recent(df_id, getattr(df, "name", ""), intent_name)
        # Render-and-cache now so this doc has a thumbnail in Recent later.
        _thumbnail_for_open_doc(doc, df_id)
    except Exception:
        pass


def _list_recent_docs() -> list[dict]:
    """Recent cache filtered to entries that are NOT currently open and have
    NOT been inserted during this palette session. Enriches each entry with a
    thumbnail URL when one is cached on disk."""
    entries = _read_recent_cache()
    # _list_open_docs already filters out _inserted_in_session, so we need a
    # raw open-id set here (re-read docs to get every truly-open id).
    raw_open_ids: set[str] = set()
    try:
        for i in range(app.documents.count):
            doc = app.documents.item(i)
            if doc is None or not doc.isSaved:
                continue
            df = getattr(doc, "dataFile", None)
            if df is None:
                continue
            raw_open_ids.add(getattr(df, "id", ""))
    except Exception:
        pass
    # Include the active doc's id too — we never want it to appear.
    try:
        active_df = getattr(app.activeDocument, "dataFile", None)
        if active_df is not None:
            raw_open_ids.add(getattr(active_df, "id", ""))
    except Exception:
        pass

    seen: set[str] = set()
    out: list[dict] = []
    # Newest first.
    for entry in reversed(entries):
        df_id = entry.get("dataFileId", "")
        if not df_id or df_id in seen:
            continue
        if df_id in raw_open_ids or df_id in _inserted_in_session:
            continue
        seen.add(df_id)
        # Recent docs are by definition not open — Component.createThumbnail
        # can't render them. Reuse whatever PNG was cached when this doc was
        # last open; otherwise the card falls back to the placeholder.
        thumb_url = _cached_thumbnail(df_id)
        out.append(
            {
                "dataFileId": df_id,
                "name": entry.get("name", ""),
                "intent": entry.get("intent", ""),
                "thumbUrl": thumb_url,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Palette → backend actions
# ---------------------------------------------------------------------------


_INTENT_MAP = {
    "part": adsk.fusion.DesignIntentTypes.PartDesignIntentType,
    "hybrid": adsk.fusion.DesignIntentTypes.HybridDesignIntentType,
    "assembly": adsk.fusion.DesignIntentTypes.AssemblyDesignIntentType,
}


def _palette_incoming(html_args: adsk.core.HTMLEventArgs):
    action = html_args.action
    try:
        data = json.loads(html_args.data) if html_args.data else {}
    except Exception:
        data = {}

    palette = ui.palettes.itemById(PALETTE_ID)

    if action == "createComponent":
        msg = _action_create_component(data)
        if msg:
            ui.messageBox(msg, CMD_NAME)
        # Refresh open-docs list — the new external doc just opened.
        if palette:
            _send_palette_init(palette)
        html_args.returnData = "OK"
        return

    if action == "launchAssemblyBuilder":
        _hide_palette(palette)
        _execute_command(_ASSEMBLY_BUILDER_CMD_ID)
        html_args.returnData = "OK"
        return

    if action == "launchGlobalParameters":
        _hide_palette(palette)
        _execute_command(_GLOBAL_PARAMETERS_CMD_ID)
        html_args.returnData = "OK"
        return

    if action == "insertDoc":
        msg = _action_insert_doc(data)
        if msg:
            ui.messageBox(msg, CMD_NAME)
        if palette:
            _send_palette_init(palette)
        html_args.returnData = "OK"
        return

    if action == "setShowChildren":
        global _show_children
        _show_children = bool(data.get("showChildren", False))
        # Only the Open list depends on this — re-send just that.
        if palette:
            palette.sendInfoToHTML("setOpenDocs", json.dumps(_list_open_docs()))
        html_args.returnData = "OK"
        return

    if action == "refresh":
        if palette:
            _send_palette_init(palette)
        html_args.returnData = "OK"
        return

    html_args.returnData = "OK"


def _hide_palette(palette) -> None:
    if palette:
        palette.isVisible = False


def _execute_command(cmd_id: str) -> None:
    cmd_def = ui.commandDefinitions.itemById(cmd_id)
    if cmd_def is None:
        ui.messageBox(f"Command '{cmd_id}' is not available.", CMD_NAME)
        return
    cmd_def.execute()


def _active_design_or_none() -> adsk.fusion.Design | None:
    product = app.activeProduct
    return adsk.fusion.Design.cast(product) if product else None


def _action_create_component(data: dict) -> str:
    name = (data.get("name") or "").strip()
    intent = data.get("intent", "part")
    if not name:
        return "Component name is required."
    fusion_intent = _INTENT_MAP.get(intent)
    if fusion_intent is None:
        return f"Unknown intent: {intent}"

    design = _active_design_or_none()
    if design is None:
        return "No active Fusion design."

    project = app.data.activeProject
    if project is None:
        return "No active Fusion project — save the active document first."
    folder = project.rootFolder
    transform = adsk.core.Matrix3D.create()
    try:
        occ = design.rootComponent.occurrences.addNewExternalComponent(
            name, folder, transform
        )
        if not occ:
            return f"Failed to create component '{name}'."
        try:
            occ.component.parentDesign.designIntent = fusion_intent
        except Exception as e:
            futil.log(f"{CMD_NAME}: could not set intent on '{name}': {e}")
        futil.log(f"{CMD_NAME}: created external '{name}' ({intent}).")
        return ""
    except Exception as e:
        return f"Create failed: {e}"


def _action_insert_doc(data: dict) -> str:
    df_id = data.get("dataFileId", "")
    if not df_id:
        return "Missing dataFileId."

    design = _active_design_or_none()
    if design is None:
        return "No active Fusion design."

    data_file = _find_data_file_by_id(df_id)
    if data_file is None:
        return "Could not resolve the selected document."

    transform = adsk.core.Matrix3D.create()
    try:
        design.rootComponent.occurrences.addByInsert(data_file, transform, True)
        intent_name = data.get("intent", "")
        _touch_recent(df_id, getattr(data_file, "name", ""), intent_name)
        # Remember this doc was inserted in this session so the next refresh
        # hides it from both galleries — a second click would silently create a
        # duplicate occurrence in the assembly.
        _inserted_in_session.add(df_id)
        futil.log(f"{CMD_NAME}: inserted '{getattr(data_file, 'name', df_id)}'.")
        return ""
    except Exception as e:
        return f"Insert failed: {e}"
