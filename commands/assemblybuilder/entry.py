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
import traceback

import adsk.core
import adsk.fusion

from ... import config
from ...lib import fusionAddInUtils as futil

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
PALETTE_URL = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "resources", "html", "index.html"
).replace("\\", "/")

local_handlers = []


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

    # Must be unsaved (new document)
    if doc.isSaved:
        ui.messageBox(
            "Assembly Builder only works on new, unsaved documents.\n\n"
            "Please create a new Design (File > New Design) and try again.",
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
    if palette is None:
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
        futil.log(
            f"{CMD_NAME}: Created a new palette: ID = {palette.id}, Name = {palette.name}"
        )

    if palette.dockingState == adsk.core.PaletteDockingStates.PaletteDockStateFloating:
        palette.dockingState = PALETTE_DOCKING

    palette.isVisible = True

    # Send document name
    palette.sendInfoToHTML("setDocumentName", doc.name)

    # Send UI theme (2 = dark, anything else = light)
    theme = app.preferences.generalPreferences.userInterfaceTheme
    palette.sendInfoToHTML("setTheme", "dark" if theme == 2 else "light")


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
            html_args.returnData = create_assembly_from_graph(graph_data)
        except Exception:
            error_msg = f"Assembly creation failed:\n{traceback.format_exc()}"
            futil.log(error_msg)
            html_args.returnData = error_msg
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


def find_root_node_id(nodes: dict) -> int:
    """Find the root node (the one with class 'is-root' or no input connections)."""
    for node_id, node in nodes.items():
        if "is-root" in (node.get("class", "") or ""):
            return int(node_id)
    for node_id, node in nodes.items():
        has_inputs = False
        for input_val in node.get("inputs", {}).values():
            if input_val.get("connections", []):
                has_inputs = True
                break
        if not has_inputs:
            return int(node_id)
    return None


def find_shared_nodes(nodes: dict, root_node_id: int) -> set:
    """Find nodes that have more than one parent (shared components)."""
    shared = set()
    for node_id in nodes:
        nid = int(node_id)
        if nid == root_node_id:
            continue
        if len(get_parent_ids(nodes, nid)) > 1:
            shared.add(nid)
    return shared


def create_assembly_from_graph(graph_data: dict) -> str:
    """
    Parse a Drawflow graph export and create the assembly hierarchy
    top-down using addNewExternalComponent. Shared nodes (connected to
    multiple parents) are created once, saved to get a DataFile, then
    inserted by reference into additional parents via addByInsert.
    """
    nodes = graph_data.get("drawflow", {}).get("Home", {}).get("data", {})
    if not nodes:
        return "Error: No nodes found in graph."

    root_node_id = find_root_node_id(nodes)
    if root_node_id is None:
        return "Error: Could not find root node in graph."

    child_ids = get_child_ids(nodes, root_node_id)
    if not child_ids:
        return "Error: Root node has no children. Add nodes before creating."

    doc = app.activeDocument
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        return "Error: No active Fusion design."

    folder = app.data.activeProject.rootFolder
    root_comp = design.rootComponent
    transform = adsk.core.Matrix3D.create()

    # Set root design intent
    root_node = nodes[str(root_node_id)]
    root_type = root_node.get("name", "root")
    design.designIntent = INTENT_MAP.get(
        root_type, adsk.fusion.DesignIntentTypes.AssemblyDesignIntentType
    )

    shared_node_ids = find_shared_nodes(nodes, root_node_id)
    has_shared = len(shared_node_ids) > 0

    created_count = 0
    # Track created nodes: node_id -> occurrence (first creation)
    created_map: dict[int, adsk.fusion.Occurrence] = {}
    # Track deferred insertions for shared nodes: [(parent_comp, node_id), ...]
    deferred_inserts: list[tuple] = []

    def create_children(parent_comp: adsk.fusion.Component, parent_node_id: int):
        nonlocal created_count
        for child_id in get_child_ids(nodes, parent_node_id):
            child_node = nodes.get(str(child_id))
            if not child_node:
                continue

            child_name = child_node.get("data", {}).get("name", f"Component_{child_id}")
            child_type = child_node.get("name", "part")

            # Shared node already created — defer insertion for after save
            if child_id in created_map:
                futil.log(
                    f"  Deferring shared insert: {child_name} into {parent_comp.name}"
                )
                deferred_inserts.append((parent_comp, child_id))
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

    # Handle shared components — requires a save to get DataFile references
    if deferred_inserts:
        futil.log(f"{CMD_NAME}: Saving to establish shared component references...")
        doc.save("Assembly Builder: saving to enable shared components")
        adsk.doEvents()

        for parent_comp, child_id in deferred_inserts:
            child_node = nodes.get(str(child_id))
            child_name = child_node.get("data", {}).get("name", f"Component_{child_id}")
            occ = created_map.get(child_id)
            if not occ:
                futil.log(f"  Shared insert failed — no occurrence for: {child_name}")
                continue

            try:
                data_file = occ.component.parentDesign.parentDocument.dataFile
                if data_file:
                    parent_comp.occurrences.addByInsert(data_file, transform, True)
                    created_count += 1
                    futil.log(
                        f"  Inserted shared ref: {child_name} into {parent_comp.name}"
                    )
                else:
                    futil.log(
                        f"  No DataFile found for shared component: {child_name}"
                    )
            except Exception as e:
                futil.log(f"  Shared insert error for {child_name}: {e}")

    # Hide the palette
    palette = ui.palettes.itemById(PALETTE_ID)
    if palette:
        palette.isVisible = False

    result_msg = f"Created {created_count} components successfully."
    if deferred_inserts:
        result_msg += f" ({len(deferred_inserts)} shared reference(s) inserted.)"
    futil.log(f"{CMD_NAME}: {result_msg}")
    return result_msg


def command_destroy(args: adsk.core.CommandEventArgs):
    futil.log(f"{CMD_NAME}: Command destroy event.")
    global local_handlers
    local_handlers = []
