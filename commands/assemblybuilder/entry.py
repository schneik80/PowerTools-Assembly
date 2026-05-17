# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

# PowerTools Assembly - Assembly Builder command.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import json
import os
import time
import traceback

import adsk.core
import adsk.fusion

from ... import config
from ...lib import fusionAddInUtils as futil
from ...lib.fusionAddInUtils import cache_utils as cache

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Assembly Builder"
CMD_ID = "PTAT-AssemblyBuilder"
CMD_Description = (
    "Design an assembly hierarchy in a visual node editor, then generate "
    "all external components with the correct design intent in one step."
)
IS_PROMOTED = False

PALETTE_NAME = "Assembly Builder"
PALETTE_ID = config.assembly_builder_palette_id
PALETTE_DOCKING = adsk.core.PaletteDockingStates.PaletteDockStateRight

WORKSPACE_ID = config.design_workspace
TAB_ID = config.tools_tab_id
TAB_NAME = config.my_tab_name
PANEL_ID = config.my_panel_id
PANEL_NAME = config.my_panel_name
PANEL_AFTER = config.my_panel_after

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")
_HTML_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "resources", "html"
)
PALETTE_URL = os.path.join(_HTML_DIR, "index.html").replace("\\", "/")
# Generated sidecar the page loads synchronously (like drawflow.min.js) to get
# its init state. Fusion's palettes.add() rejects a query string on the URL, so
# this is how we hand the page deterministic state with no message round-trip.
INIT_JS_PATH = os.path.join(_HTML_DIR, "init.js")

local_handlers = []

# Global-parameter documents available in the active project, populated when
# the palette is shown so create-time can resolve a node's param set.
# name -> adsk.core.DataFile
_param_doc_map: dict = {}
_active_project_ref = None


def start():
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )
    futil.add_handler(cmd_def.commandCreated, command_created)

    workspace = ui.workspaces.itemById(WORKSPACE_ID)

    toolbar_tab = workspace.toolbarTabs.itemById(TAB_ID)
    if toolbar_tab is None:
        toolbar_tab = workspace.toolbarTabs.add(TAB_ID, TAB_NAME)

    panel = toolbar_tab.toolbarPanels.itemById(PANEL_ID)
    if panel is None:
        panel = toolbar_tab.toolbarPanels.add(PANEL_ID, PANEL_NAME, PANEL_AFTER, False)

    control = panel.controls.addCommand(cmd_def)
    control.isPromoted = IS_PROMOTED


def stop():
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    toolbar_tab = workspace.toolbarTabs.itemById(TAB_ID)
    command_control = panel.controls.itemById(CMD_ID) if panel else None
    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    palette = ui.palettes.itemById(PALETTE_ID)

    if command_control:
        command_control.deleteMe()

    if command_definition:
        command_definition.deleteMe()

    if palette:
        palette.deleteMe()

    if panel and panel.controls.count == 0:
        panel.deleteMe()

    if toolbar_tab and toolbar_tab.toolbarPanels.count == 0:
        toolbar_tab.deleteMe()


def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f"{CMD_NAME}: Command created event.")
    futil.add_handler(
        args.command.execute, command_execute, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )


def _design_is_empty(design: adsk.fusion.Design) -> bool:
    """True if the root component has nothing modeled — no child components,
    bodies, sketches, or timeline features."""
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
        # Direct-modeling designs have no timeline — bodies/sketches above
        # already cover "has something modeled".
        pass
    return True


def command_execute(args: adsk.core.CommandEventArgs):
    futil.log(f"{CMD_NAME}: Command execute event.")

    # Must be a Fusion Design
    product = app.activeProduct
    if not product or not isinstance(product, adsk.fusion.Design):
        ui.messageBox(
            "Assembly Builder requires an active Fusion Design.\n\n"
            "Please open or create a Design first.",
            CMD_NAME,
        )
        return

    design = adsk.fusion.Design.cast(product)
    doc = app.activeDocument

    # Normally a new, unsaved document. Special case: a *saved* document is
    # allowed too, but only if it is still empty (no features or child
    # components) — anything already modeled would be disrupted.
    if doc.isSaved and not _design_is_empty(design):
        ui.messageBox(
            "Assembly Builder works on a new document, or a saved document "
            "that is still empty.\n\n"
            "The active design is saved and already has features or "
            "components. Please start with a new or empty Design.",
            CMD_NAME,
        )
        return

    # Must be Assembly or Hybrid intent
    if design.designIntent == adsk.fusion.DesignIntentTypes.PartDesignIntentType:
        ui.messageBox(
            "Assembly Builder requires an Assembly or Hybrid document.\n\n"
            "The active design has Part intent. Please change the design intent "
            "to Assembly or Hybrid, or create a new document.",
            CMD_NAME,
        )
        return

    # Must have no existing children
    root_comp = design.rootComponent
    if root_comp.occurrences.count > 0:
        ui.messageBox(
            "Assembly Builder only works on empty documents.\n\n"
            "The active design already has components. "
            "Please start with a new, empty Design.",
            CMD_NAME,
        )
        return

    palettes = ui.palettes
    palette = palettes.itemById(PALETTE_ID)
    just_created = palette is None

    if just_created:
        # Write the init sidecar BEFORE creating the palette so index.html
        # loads it synchronously on first paint — no sendInfoToHTML round-trip,
        # no handshake, no theme/param flicker. (Reopen handled by the push
        # below.)
        _write_init_js(_gather_palette_state())
        palette = palettes.add(
            id=PALETTE_ID,
            name=PALETTE_NAME,
            htmlFileURL=PALETTE_URL,
            isVisible=True,
            showCloseButton=True,
            isResizable=True,
            width=800,
            height=600,
            useNewWebBrowser=True,
        )
        futil.add_handler(palette.closed, palette_closed)
        futil.add_handler(palette.navigatingURL, palette_navigating)
        futil.add_handler(palette.incomingFromHTML, palette_incoming)
        # Keep the palette's save-required gate in sync when the user saves.
        futil.add_handler(app.documentSaved, document_saved)
        futil.log(
            f"{CMD_NAME}: Created a new palette: ID = {palette.id}, Name = {palette.name}"
        )

    if palette.dockingState == adsk.core.PaletteDockingStates.PaletteDockStateFloating:
        palette.dockingState = PALETTE_DOCKING

    palette.isVisible = True

    if not just_created:
        # The page is already loaded from a previous show, so an immediate
        # push has no race — refresh doc name / theme / save state / params.
        _send_palette_init(palette)


def _os_is_dark() -> bool:
    """Best-effort OS dark-mode detection (for the 'match device' theme)."""
    import sys

    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                # AppsUseLightTheme: 1 = light, 0 = dark.
                val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return val == 0
        except Exception:
            return True  # Fusion's modern default look is dark
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


def _gather_palette_state() -> dict:
    """Collect the deterministic init state for the palette in one place."""
    doc = app.activeDocument

    # userInterfaceTheme is one of: Classic(0)/LightGray(1) = light,
    # DarkBlue(2)/DarkGray(3) = dark, Device(4) = follow the OS.
    themes = adsk.core.UserInterfaceThemes
    theme = app.preferences.generalPreferences.userInterfaceTheme
    if theme == themes.DeviceUserInterfaceTheme:
        is_dark = _os_is_dark()
        source = "device/os"
    else:
        is_dark = theme in (
            themes.DarkBlueUserInterfaceTheme,
            themes.DarkGrayUserInterfaceTheme,
        )
        source = "explicit"
    futil.log(
        f"{CMD_NAME}: theme raw={int(theme)} ({source}) "
        f"-> {'dark' if is_dark else 'light'}"
    )

    # Discover existing global-parameter documents in the active project.
    global _param_doc_map, _active_project_ref
    _param_doc_map = {}
    _active_project_ref = cache.get_active_project(CMD_NAME)
    param_entries = []
    if _active_project_ref is None:
        futil.log(f"{CMD_NAME}: no active project — cannot list parameter docs.")
    else:
        try:
            _param_doc_map = cache.list_param_docs(_active_project_ref, CMD_NAME)
            param_entries = [
                {"id": getattr(df, "id", ""), "name": name}
                for name, df in _param_doc_map.items()
            ]
            futil.log(
                f"{CMD_NAME}: found {len(param_entries)} parameter doc(s) in "
                f"project '{_active_project_ref.name}'."
            )
        except Exception as e:
            futil.log(f"{CMD_NAME}: could not list parameter docs — {e}")

    return {
        "docName": doc.name,
        "theme": "dark" if is_dark else "light",
        "saved": bool(doc.isSaved),
        "paramDocs": param_entries,
    }


def _write_init_js(state: dict) -> None:
    """Write resources/html/init.js exposing the init state as window.__ptInit.

    The page loads this via <script src="init.js"> (same as drawflow.min.js),
    so the state is available synchronously before first paint. As an external
    script there is no HTML parser, so embedded '</script>' in names is safe.
    """
    try:
        payload = json.dumps(state)
        with open(INIT_JS_PATH, "w", encoding="utf-8") as fh:
            fh.write(f"window.__ptInit = {payload};\n")
    except Exception as e:
        futil.log(f"{CMD_NAME}: could not write init.js — {e}")


def _send_palette_init(palette: adsk.core.Palette):
    """Push the gathered state to an already-loaded palette page."""
    state = _gather_palette_state()
    palette.sendInfoToHTML("setDocumentName", state["docName"])
    palette.sendInfoToHTML("setTheme", state["theme"])
    palette.sendInfoToHTML(
        "setSaveState", "saved" if state["saved"] else "unsaved"
    )
    palette.sendInfoToHTML("setParamDocs", json.dumps(state["paramDocs"]))


def document_saved(args: adsk.core.DocumentEventArgs):
    """Push the active document's save state to the palette gate."""
    palette = ui.palettes.itemById(PALETTE_ID)
    if not palette:
        return
    doc = app.activeDocument
    state = "saved" if (doc and doc.isSaved) else "unsaved"
    futil.log(f"{CMD_NAME}: Document saved — notifying palette ({state}).")
    palette.sendInfoToHTML("setSaveState", state)


def palette_closed(args: adsk.core.UserInterfaceGeneralEventArgs):
    futil.log(f"{CMD_NAME}: Palette was closed.")


def palette_navigating(args: adsk.core.NavigationEventArgs):
    url = args.navigationURL
    futil.log(f"{CMD_NAME}: Palette navigating to {url}")
    if url.startswith("http"):
        args.launchExternally = True


def palette_incoming(html_args: adsk.core.HTMLEventArgs):
    futil.log(f"{CMD_NAME}: Palette incoming event.")

    message_action = html_args.action

    if message_action == "createAssembly":
        try:
            graph_data = json.loads(html_args.data)
            message = create_assembly_from_graph(graph_data)
        except Exception:
            futil.log(f"Assembly creation failed:\n{traceback.format_exc()}")
            message = "Error: Assembly creation failed. See the Text Commands log for details."

        # Show every outcome as a native Fusion dialog rather than the
        # palette's browser alert(). "OK" is the silent sentinel returned by
        # the save-needed path, so there is nothing to report.
        if message and message != "OK":
            is_error = message.startswith("Error:")
            ui.messageBox(
                message,
                CMD_NAME,
                adsk.core.MessageBoxButtonTypes.OKButtonType,
                adsk.core.MessageBoxIconTypes.CriticalIconType
                if is_error
                else adsk.core.MessageBoxIconTypes.InformationIconType,
            )

        # Always hand the JS no-op sentinel back so the palette never alerts.
        html_args.returnData = "OK"
        return

    # Default handler for other messages
    message_data: dict = json.loads(html_args.data)
    futil.log(
        f"Action: {message_action}, Data: {message_data}",
        adsk.core.LogLevels.InfoLogLevel,
    )
    html_args.returnData = "OK"


# ---------------------------------------------------------------------------
# Assembly creation from Drawflow graph
# ---------------------------------------------------------------------------

INTENT_MAP = {
    "part": adsk.fusion.DesignIntentTypes.PartDesignIntentType,
    "assembly": adsk.fusion.DesignIntentTypes.AssemblyDesignIntentType,
    "hybrid": adsk.fusion.DesignIntentTypes.HybridDesignIntentType,
}


def get_child_ids(nodes: dict, parent_id: int) -> list:
    """Get child node IDs from a parent node's output connections."""
    parent = nodes.get(str(parent_id), {})
    children = []
    for output_val in parent.get("outputs", {}).values():
        for conn in output_val.get("connections", []):
            children.append(int(conn["node"]))
    return children


def get_parent_ids(nodes: dict, node_id: int) -> list:
    """Get parent node IDs from a node's input connections."""
    node = nodes.get(str(node_id), {})
    parents = []
    for input_val in node.get("inputs", {}).values():
        for conn in input_val.get("connections", []):
            parents.append(int(conn["node"]))
    return parents


def is_param_node(nodes: dict, node_id: int) -> bool:
    """True if *node_id* is a global-parameter source node."""
    return nodes.get(str(node_id), {}).get("name") == "paramdoc"


def get_structural_child_ids(nodes: dict, parent_id: int) -> list:
    """Child component IDs of *parent_id*, excluding param-doc links."""
    return [
        cid
        for cid in get_child_ids(nodes, parent_id)
        if not is_param_node(nodes, cid)
    ]


def get_structural_parent_ids(nodes: dict, node_id: int) -> list:
    """Parent IDs of *node_id*, excluding param-doc sources.

    Param-doc links land on the same input port as the structural parent, so
    they must be filtered out before counting parents.
    """
    return [
        pid
        for pid in get_parent_ids(nodes, node_id)
        if not is_param_node(nodes, pid)
    ]


def collect_param_links(nodes: dict) -> dict:
    """Map target component node id -> list of param-doc node dicts.

    A param-doc node's output connections point at the component nodes that
    should have that parameter set derived into them.
    """
    links: dict[int, list] = {}
    for node_id, node in nodes.items():
        if node.get("name") != "paramdoc":
            continue
        for output_val in node.get("outputs", {}).values():
            for conn in output_val.get("connections", []):
                target = int(conn["node"])
                links.setdefault(target, []).append(node)
    return links


def find_root_node_id(nodes: dict) -> int:
    """Find the root node (class 'is-root' or no input connections)."""
    for node_id, node in nodes.items():
        if "is-root" in (node.get("class", "") or ""):
            return int(node_id)
    for node_id, node in nodes.items():
        if node.get("name") == "paramdoc":
            continue  # a parameter source is never the root
        has_inputs = False
        for input_val in node.get("inputs", {}).values():
            if input_val.get("connections", []):
                has_inputs = True
                break
        if not has_inputs:
            return int(node_id)
    return None


def find_shared_nodes(nodes: dict, root_node_id: int) -> set:
    """Find component nodes that have more than one structural parent."""
    shared = set()
    for node_id in nodes:
        nid = int(node_id)
        if nid == root_node_id or is_param_node(nodes, nid):
            continue
        if len(get_structural_parent_ids(nodes, nid)) > 1:
            shared.add(nid)
    return shared


def _resolve_param_data_file(param_node: dict):
    """Resolve a param-doc graph node to its Fusion DataFile, or None."""
    global _param_doc_map
    data = param_node.get("data", {})
    name = data.get("paramName") or data.get("name")
    pid = data.get("paramId")

    df = _param_doc_map.get(name) if name else None
    if df is not None:
        return df

    for finder_owner in (
        getattr(_active_project_ref, "data", None),
        getattr(app, "data", None),
    ):
        finder = getattr(finder_owner, "findFileById", None)
        if pid and callable(finder):
            try:
                df = finder(pid)
                if df:
                    return df
            except Exception:
                pass

    # Last resort: rescan the project's parameter folder.
    if _active_project_ref is not None and name:
        try:
            _param_doc_map = cache.list_param_docs(_active_project_ref, CMD_NAME)
            return _param_doc_map.get(name)
        except Exception:
            return None
    return None


def _derive_param_set(target_design: adsk.fusion.Design, params_data_file) -> None:
    """Derive favorite parameters from *params_data_file* into *target_design*.

    Mirrors linkGlobalParameters._derive_into_active: open the params doc,
    create a derive input with favorite parameters, insert it first in the
    timeline, then close the params doc.
    """
    params_doc = app.documents.open(params_data_file, False)
    try:
        params_design = adsk.fusion.Design.cast(
            params_doc.products.itemByProductType("DesignProductType")
        )
        if params_design is None:
            raise RuntimeError("Could not obtain Design from the parameters document.")

        derive_features = target_design.rootComponent.features.deriveFeatures
        derive_input = derive_features.createInput(params_design)
        derive_input.isIncludeFavoriteParameters = True
        timeline = target_design.timeline
        timeline.markerPosition = 0
        derive_features.add(derive_input)
        timeline.markerPosition = timeline.count
    finally:
        params_doc.close(False)


def _resolve_target_data_file(occ, label: str, progress=None):
    """Return the DataFile for a freshly-flushed external component, or None.

    The root save uploads child documents to the cloud ASYNCHRONOUSLY, and
    that pipeline only advances while we pump adsk.doEvents() (see
    externalize._save_to_cloud). Until the upload finishes,
    parentDocument.dataFile raises "Failed to get temporary file" — that race
    (not a stale proxy: the original code opened the first target's DataFile
    fine) is why only the first param target worked. So spin on doEvents()
    until the DataFile is available, trying each property INDEPENDENTLY
    because Fusion attribute access raises rather than returning None.

    Returns the DataFile *object* (not its id): data-panel DataFile objects
    survive document open/close, and a just-flushed doc's id is not yet
    resolvable via app.data.findFileById ("file not found").
    """
    t0 = time.monotonic()
    last_hb = t0
    while True:
        for attr in ("dataFile", "designDataFile"):
            try:
                pdoc = occ.component.parentDesign.parentDocument
                ddf = getattr(pdoc, attr)
                if ddf is not None and getattr(ddf, "id", ""):
                    return ddf
            except Exception:
                pass
        if progress is not None and progress.wasCancelled:
            return None
        now = time.monotonic()
        if now - t0 > 120.0:  # generous cap; uploads are usually seconds
            return None
        if now - last_hb >= 5.0:
            futil.log(
                f"{CMD_NAME}: waiting for '{label}' to finish flushing "
                f"({now - t0:.0f}s)…"
            )
            last_hb = now
        adsk.doEvents()


def _derive_param_links(
    param_links: dict,
    root_node_id: int,
    root_design: adsk.fusion.Design,
    created_map: dict,
    root_doc: adsk.core.Document,
) -> tuple:
    """Third pass: derive each linked parameter set into its target document,
    with a progress dialog, then pull latest refs into the root and save it.

    Returns (derived_count, error_messages).
    """
    derived = 0
    errors: list[str] = []

    # Show progress up front: resolving each external doc's id requires a
    # doEvents() spin (async cloud flush), so the dialog must already be live
    # to report status and honor Cancel.
    progress = ui.createProgressDialog()
    progress.isCancelButtonShown = True
    progress.cancelButtonText = "Cancel"
    progress.isBackgroundTranslucent = False
    progress.show(
        f"{CMD_NAME} — Global Parameters",
        "Waiting for new components to finish flushing…",
        0,
        max(len(param_links), 1) + 1,
        0,
    )

    # Build work items, capturing DataFile objects now (they survive the
    # open/close churn that invalidates design/occurrence proxies).
    work: list[tuple] = []  # [(data_file, [(pname, param_df), ...])]
    root_items: list[tuple] = []  # [(pname, param_df)] — derive into root
    for target_id, param_nodes in param_links.items():
        resolved = []
        for pn in param_nodes:
            pdf = _resolve_param_data_file(pn)
            pname = pn.get("data", {}).get("paramName", "?")
            if pdf is None:
                errors.append(f"could not resolve parameter set '{pname}'")
            else:
                resolved.append((pname, pdf))
        if not resolved:
            continue

        if target_id == root_node_id:
            root_items.extend(resolved)
            continue

        occ = created_map.get(target_id)
        if occ is None:
            errors.append(f"param target node {target_id} was not created")
            continue
        try:
            label = occ.component.name
        except Exception:
            label = f"component {target_id}"
        progress.message = f"Preparing '{label}'…"
        data_file = _resolve_target_data_file(occ, label, progress)
        if data_file is None:
            errors.append(
                f"no DataFile for param target {target_id} "
                f"(external doc not flushed)"
            )
            continue
        work.append((data_file, resolved))

    # One progress step per external document, plus a final "update assembly".
    total = len(work) + 1
    progress.maximumValue = total
    progress.progressValue = 0

    # Root-targeted sets (rare; the UI can't normally make them).
    for pname, pdf in root_items:
        try:
            _derive_param_set(root_design, pdf)
            derived += 1
            futil.log(f"  Derived '{pname}' into root")
        except Exception as e:
            errors.append(f"derive '{pname}' into root failed: {e}")

    done = 0
    for data_file, resolved in work:
        if progress.wasCancelled:
            errors.append("cancelled before all parameters were derived")
            break
        name = getattr(data_file, "name", None) or "external component"
        progress.message = (
            f"Deriving parameters into '{name}' ({done + 1} of {len(work)})"
        )
        target_doc = None
        try:
            target_doc = app.documents.open(data_file, True)
            target_design = adsk.fusion.Design.cast(
                target_doc.products.itemByProductType("DesignProductType")
            )
            if target_design is None:
                errors.append(f"no Design for '{name}'")
            else:
                for pname, pdf in resolved:
                    try:
                        _derive_param_set(target_design, pdf)
                        derived += 1
                        futil.log(f"  Derived '{pname}' into {name}")
                    except Exception as e:
                        errors.append(
                            f"derive '{pname}' into {name} failed: {e}"
                        )
                # Save AND wait for the cloud upload to commit — otherwise
                # the root's updateAllReferences() below would pull a stale
                # version of (especially) the last component.
                try:
                    pre_ver = target_doc.dataFile.versionNumber
                except Exception:
                    pre_ver = None
                progress.message = f"Uploading '{name}'…"
                save_result = target_doc.save("Updated with Assembly Builder")
                ok, msg = futil.wait_for_upload(
                    save_result,
                    name,
                    document=target_doc,
                    pre_save_version=pre_ver,
                    log_fn=futil.log,
                )
                if not ok:
                    errors.append(f"upload wait for '{name}': {msg}")
        except Exception as e:
            errors.append(f"'{name}' open/save failed: {e}")
        finally:
            if target_doc is not None:
                try:
                    target_doc.close(False)
                except Exception:
                    pass
            adsk.doEvents()
        done += 1
        progress.progressValue = done

    # Final step: back on the root assembly, pull all references to latest
    # and save with a clear comment.
    progress.message = "Updating assembly references to latest…"
    cache.safe_activate(root_doc, CMD_NAME)
    adsk.doEvents()
    try:
        root_doc.updateAllReferences()
    except Exception as e:
        futil.log(f"{CMD_NAME}: updateAllReferences failed: {e}")
    try:
        root_doc.save("Updated with Assembly Builder")
    except Exception as e:
        futil.log(f"{CMD_NAME}: final root save failed: {e}")
    progress.progressValue = total
    progress.hide()

    return derived, errors


def create_assembly_from_graph(graph_data: dict) -> str:
    """
    Parse a Drawflow graph export and create the assembly hierarchy.

    Pass 1 builds the tree top-down with addNewExternalComponent, creating
    each shared node's first instance and recording later encounters.
    A save then flushes every new external document to a DataFile. Pass 2
    inserts each shared component by reference (addByInsert) into its other
    parents — addByInsert requires a DataFile, which only exists post-save.
    Pass 3 opens each component that links a global-parameter set and derives
    those favorite parameters into it (root links derive into the root).
    The root is saved up front when shared parts or parameter sets are present
    so none of these saves trigger Fusion's save-as dialog.
    """
    nodes = graph_data.get("drawflow", {}).get("Home", {}).get("data", {})
    if not nodes:
        return "Error: No nodes found in graph."

    root_node_id = find_root_node_id(nodes)
    if root_node_id is None:
        return "Error: Could not find root node in graph."

    child_ids = get_structural_child_ids(nodes, root_node_id)
    if not child_ids:
        return "Error: Root node has no children. Add nodes before creating."

    doc = app.activeDocument
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        return "Error: No active Fusion design."

    # Detect shared (reused) parts and global-parameter links. Both need the
    # root document to have a DataFile (shared: addByInsert; params: open the
    # external component to derive). The palette shows a banner and disables
    # Create until saved — this is a defensive fallback if that gate is missed.
    shared_node_ids = find_shared_nodes(nodes, root_node_id)
    has_shared = len(shared_node_ids) > 0
    param_links = collect_param_links(nodes)

    if (has_shared or param_links) and not doc.isSaved:
        return (
            "Error: This design has shared parts or global parameters and "
            "must be saved first. Save the document (Ctrl+S) and try again."
        )

    folder = app.data.activeProject.rootFolder
    root_comp = design.rootComponent
    transform = adsk.core.Matrix3D.create()

    # Set root design intent
    root_node = nodes[str(root_node_id)]
    root_type = root_node.get("name", "root")
    design.designIntent = INTENT_MAP.get(
        root_type, adsk.fusion.DesignIntentTypes.AssemblyDesignIntentType
    )

    created_count = 0
    shared_insert_count = 0
    # Track created nodes: node_id -> occurrence (first creation)
    created_map: dict[int, adsk.fusion.Occurrence] = {}
    # Repeat encounters of a shared node, resolved after a save flushes the
    # first instance's external document to a DataFile.
    #   [(parent_node_id, parent_comp, child_id), ...]
    deferred_inserts: list[tuple] = []

    def create_children(parent_comp: adsk.fusion.Component, parent_node_id: int):
        nonlocal created_count
        for child_id in get_child_ids(nodes, parent_node_id):
            child_node = nodes.get(str(child_id))
            if not child_node:
                continue

            # Parameter-source nodes are handled in pass 3, not structurally.
            if is_param_node(nodes, child_id):
                continue

            child_name = child_node.get("data", {}).get("name", f"Component_{child_id}")
            child_type = child_node.get("name", "part")

            # Shared node already created once. Its external document has no
            # DataFile until the root is saved, so addByInsert can't run yet —
            # defer it to the second pass.
            if child_id in created_map:
                futil.log(
                    f"  Deferring shared insert: {child_name} into {parent_comp.name}"
                )
                deferred_inserts.append((parent_node_id, parent_comp, child_id))
                continue

            futil.log(f"  Creating external component: {child_name} ({child_type})")

            occ = parent_comp.occurrences.addNewExternalComponent(
                child_name, folder, transform
            )
            if not occ:
                futil.log(f"  Failed to create: {child_name}")
                continue

            created_count += 1
            created_map[child_id] = occ
            child_comp = occ.component

            # Set design intent
            intent = INTENT_MAP.get(child_type)
            if intent is not None:
                try:
                    child_comp.parentDesign.designIntent = intent
                    futil.log(f"  Set {child_type} intent on {child_name}")
                except Exception as e:
                    futil.log(f"  Failed to set intent on {child_name}: {e}")

            # Recurse for assemblies/hybrids
            if child_type in ("assembly", "hybrid"):
                create_children(child_comp, child_id)

    futil.log(f"{CMD_NAME}: Creating assembly hierarchy...")
    if has_shared:
        futil.log(f"{CMD_NAME}: Shared nodes detected: {shared_node_ids}")
    create_children(root_comp, root_node_id)

    # Second/third passes both need every freshly-created external document
    # flushed to a DataFile. One save does that for shared inserts and for
    # opening components that link a parameter set (root-only param links
    # derive into the already-saved root, so they don't need the flush).
    external_param_targets = [t for t in param_links if t != root_node_id]
    need_flush = bool(deferred_inserts) or bool(external_param_targets)
    if need_flush:
        futil.log(
            f"{CMD_NAME}: Saving to flush {len(created_map)} external "
            f"component(s) before shared inserts / parameter derivation..."
        )
        try:
            doc.save("Assembly Builder: flushing components")
        except Exception as e:
            futil.log(f"{CMD_NAME}: Flush save failed: {e}")
        adsk.doEvents()

    # Pass 2: insert shared components by reference into their other parents.
    if deferred_inserts:
        for parent_node_id, parent_comp, child_id in deferred_inserts:
            child_node = nodes.get(str(child_id))
            child_name = child_node.get("data", {}).get(
                "name", f"Component_{child_id}"
            )
            src_occ = created_map.get(child_id)
            if not src_occ:
                futil.log(f"  Shared insert skipped — no source for: {child_name}")
                continue

            # Re-derive the parent component fresh from the saved tree in case
            # the proxy captured during pass 1 went stale across the save.
            if parent_node_id == root_node_id:
                target_comp = design.rootComponent
            elif parent_node_id in created_map:
                target_comp = created_map[parent_node_id].component
            else:
                target_comp = parent_comp

            try:
                data_file = src_occ.component.parentDesign.parentDocument.dataFile
                if not data_file:
                    futil.log(
                        f"  No DataFile for shared component: {child_name} "
                        f"(external doc not flushed)"
                    )
                    continue
                target_comp.occurrences.addByInsert(data_file, transform, True)
                shared_insert_count += 1
                futil.log(
                    f"  Inserted shared ref: {child_name} into {target_comp.name}"
                )
            except Exception as e:
                futil.log(f"  Shared insert error for {child_name}: {e}")

    # Pass 3: derive global parameters into the components that link them.
    derived_count = 0
    param_errors: list[str] = []
    if param_links:
        futil.log(f"{CMD_NAME}: Deriving global parameters into linked components...")
        # _derive_param_links shows its own progress dialog and, as its final
        # step, pulls latest references into the root and saves it.
        derived_count, param_errors = _derive_param_links(
            param_links, root_node_id, design, created_map, doc
        )

    # Hide the palette
    palette = ui.palettes.itemById(PALETTE_ID)
    if palette:
        palette.isVisible = False

    result_msg = f"Created {created_count} components successfully."
    if shared_insert_count:
        result_msg += f" ({shared_insert_count} shared reference(s) inserted.)"
    elif deferred_inserts:
        result_msg += (
            f" Warning: {len(deferred_inserts)} shared reference(s) could "
            f"not be inserted — see Text Commands log."
        )
    if derived_count:
        result_msg += f" ({derived_count} global parameter set(s) derived.)"
    if param_errors:
        for err in param_errors:
            futil.log(f"  Param link issue: {err}")
        result_msg += (
            f" Warning: {len(param_errors)} parameter link(s) failed — "
            f"see Text Commands log."
        )
    futil.log(f"{CMD_NAME}: {result_msg}")
    return result_msg


def command_destroy(args: adsk.core.CommandEventArgs):
    futil.log(f"{CMD_NAME}: Command destroy event.")
    global local_handlers
    local_handlers = []
