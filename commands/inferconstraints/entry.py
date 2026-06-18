# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

# PowerTools Assembly - Infer Constraints command.
#
# Scans an already-positioned assembly (for example a STEP import whose
# components sit in their final spatial position but carry no relationships)
# and infers assembly constraints from the B-rep geometry that is already
# mating in the current pose.  Two detectors ship in this version:
#
#   * Concentric  - coaxial cylindrical faces (shaft-in-hole / pin-in-bore).
#   * Coincident  - planar faces lying flush against one another.
#
# Inferred relationships are shown in a preview table; the user selects which
# to apply.  Each applied relationship becomes an Autodesk Fusion **Assembly
# Constraint** that references the matching faces and captures the current gap
# as the constraint offset, so the components do NOT move when the constraint
# is created and the relationship re-solves if the referenced geometry later
# changes.
#
# NOTE: the assembly-constraint *creation* API (Component.assemblyConstraints
# .createInput / GeometricRelationships) is a Fusion *preview* capability
# introduced July 2025.  Autodesk warns it may change and advises against
# distributing programs that depend on it until it is released.  The apply
# path below is written against the documented preview surface and is isolated
# in _apply_candidate(); the exact isMate / isFlipped / offset semantics are
# flagged "VERIFY AT RUNTIME" and should be confirmed against a live Fusion
# build before this command ships broadly.
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

import math
import os

import adsk.core
import adsk.fusion

from ... import config
from ...lib import fusionAddInUtils as futil

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Infer Constraints"
CMD_ID = "PTAT-inferConstraints"
CMD_Description = (
    "Infer assembly constraints for an already-positioned assembly: detect "
    "concentric cylindrical faces and coincident planar faces, then apply "
    "position-preserving constraints to the pairs you select."
)
IS_PROMOTED = False

# Global UI placement, pulled from config.py (Design > Utilities > Power Tools).
WORKSPACE_ID = config.design_workspace
TAB_ID = config.tools_tab_id
TAB_NAME = config.my_tab_name
PANEL_ID = config.my_panel_id
PANEL_NAME = config.my_panel_name
PANEL_AFTER = config.my_panel_after

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")
JOINTS_ICON_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "resources", "joints"
)

# Selectable joint motion types for "joint" rows (centered coincident pairs).
# (label, icon subfolder under resources/joints). Order = dropdown order;
# the first entry (Rigid) is the default selection.
JOINT_TYPES = [
    ("Rigid", "JointRigid"),
    ("Revolute", "JointRevolute"),
    ("Slider", "JointSlider"),
    ("Cylindrical", "JointCylindrical"),
    ("Pin-Slot", "JointPin-Slot"),
    ("Planar", "JointPlanar"),
    ("Ball", "JointBall"),
]
DEFAULT_JOINT_TYPE = "Rigid"

# Command-input ids.
LIN_TOL_ID = "ic_lin_tol"
ANG_TOL_ID = "ic_ang_tol"
RESCAN_ID = "ic_rescan"
PREVIEW_SEL_ID = "ic_preview_sel"
TABLE_ID = "ic_table"
SUMMARY_ID = "ic_summary"
HEADER_ROW = 0

# Default inference tolerances.  Kernel coincidence tolerances (~1e-7 mm) are
# far too tight for imported geometry, so we use looser, user-adjustable
# values (see CAD-Mate-Inference research, Part 2 A.5).  Fusion's internal
# length unit is centimetres and angles are radians; ValueInput/command-input
# .value already returns internal units, so these defaults are expressed that
# way: 0.01 cm = 0.1 mm linear, 0.5 deg angular.
DEFAULT_LIN_TOL_CM = 0.01
DEFAULT_ANG_TOL_RAD = math.radians(0.5)

# Confidence at/above which a candidate row is checked by default.
AUTO_CHECK_CONF = 0.6

# Guard rail for very large assemblies: the broad phase is O(n^2) over
# analytic faces.  Above this count we still run, but log that it may be slow.
FACE_WARN_COUNT = 4000

local_handlers = []

# Inference results for the open dialog: list of candidate dicts.  Each row's
# checkbox id is stored on the candidate so command_execute can read it back.
_candidates: list = []
_row_counter = 0


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
def start():
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )
    futil.add_handler(cmd_def.commandCreated, command_created)

    panel = futil.get_or_create_panel(
        WORKSPACE_ID, TAB_ID, TAB_NAME, PANEL_ID, PANEL_NAME, PANEL_AFTER
    )
    if panel:
        control = panel.controls.addCommand(cmd_def)
        control.isPromoted = IS_PROMOTED


def stop():
    futil.remove_from_panel(WORKSPACE_ID, PANEL_ID, TAB_ID, CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    if command_definition:
        command_definition.deleteMe()


def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f"{CMD_NAME} Command Created Event")

    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        ui.messageBox("A Fusion 3D Design must be active.", CMD_NAME)
        return

    cmd = args.command
    inputs = cmd.commandInputs

    futil.add_handler(cmd.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(
        cmd.inputChanged, command_input_changed, local_handlers=local_handlers
    )
    futil.add_handler(cmd.destroy, command_destroy, local_handlers=local_handlers)

    # Tolerance controls.  Changing either re-runs the scan.
    inputs.addValueInput(
        LIN_TOL_ID,
        "Linear tolerance",
        "mm",
        adsk.core.ValueInput.createByReal(DEFAULT_LIN_TOL_CM),
    )
    inputs.addValueInput(
        ANG_TOL_ID,
        "Angular tolerance",
        "deg",
        adsk.core.ValueInput.createByReal(DEFAULT_ANG_TOL_RAD),
    )
    rescan = inputs.addBoolValueInput(RESCAN_ID, "Re-scan", False)
    rescan.tooltip = "Re-run detection with the current tolerances."

    # Selection input used purely to highlight the selected row's component pair
    # in the graphics. ui.activeSelections does not highlight while a command
    # dialog is open, but a SelectionCommandInput's addSelection() does. Min 0 so
    # it never blocks OK; the user can ignore it.
    sel = inputs.addSelectionInput(PREVIEW_SEL_ID, "Highlighted pair", "")
    sel.addSelectionFilter("Occurrences")
    sel.setSelectionLimits(0, 0)
    sel.tooltip = "Shows the components for the row you select in the list below."

    # Preview table: Apply | Type | Components | Confidence.
    # The Components cell is a clickable button - pressing it highlights that
    # relationship's pair in the graphics.
    table = adsk.core.TableCommandInput.cast(
        inputs.addTableCommandInput(TABLE_ID, "Inferred relationships", 4, "2:3:7:2")
    )
    table.minimumVisibleRows = 4
    table.maximumVisibleRows = 14
    table.columnSpacing = 1
    # No grid: joint rows are taller (they hold a dropdown) than constraint
    # rows, so grid separator lines would be unevenly spaced.
    table.hasGrid = False
    _add_header_row(inputs, table)

    summary = inputs.addTextBoxCommandInput(SUMMARY_ID, "Summary", "", 4, True)
    summary.isFullWidth = True

    try:
        _rescan(design, inputs)
    except Exception as scan_err:
        futil.log(f"{CMD_NAME}: scan failed - {scan_err}")
        summary.text = f"Scan failed: {scan_err}"


def command_input_changed(args: adsk.core.InputChangedEventArgs):
    try:
        changed = args.input

        # Highlight a relationship's component pair in the graphics when its row
        # is touched. Fusion does not reliably fire inputChanged on bare table
        # row-selection, so we also trigger off the row's checkbox / joint
        # dropdown (which always fire) - clicking either highlights the pair.
        if changed.id == TABLE_ID:
            _highlight_selected_row(args.inputs, adsk.core.TableCommandInput.cast(changed))
            return
        cand = _candidate_for_input(changed.id)
        if cand is not None:
            # Reset the momentary components button so it can be clicked again.
            if changed.id == cand.get("comp_btn_id"):
                adsk.core.BoolValueCommandInput.cast(changed).value = False
            _highlight_candidate(args.inputs, cand)
            return

        if changed.id not in (LIN_TOL_ID, ANG_TOL_ID, RESCAN_ID):
            return
        if changed.id == RESCAN_ID:
            # Momentary button - reset so it can be pressed again.
            adsk.core.BoolValueCommandInput.cast(changed).value = False

        design = adsk.fusion.Design.cast(app.activeProduct)
        if design:
            _rescan(design, args.inputs)
    except Exception:
        if ui:
            futil.handle_error(CMD_NAME, show_message_box=True)


def _candidate_for_input(input_id):
    """Find the candidate whose row owns the given cell-input id (checkbox or
    joint dropdown)."""
    for c in _candidates:
        if input_id in (c.get("chk_id"), c.get("joint_dd_id"), c.get("comp_btn_id")):
            return c
    return None


def _candidate_occurrences(cand):
    """The occurrence(s) a candidate touches (one for Ground, the pair otherwise)."""
    occs = []
    if cand.get("type") == "Ground":
        if cand.get("occ"):
            occs.append(cand["occ"])
        return occs
    for face in (cand.get("face_a"), cand.get("face_b")):
        try:
            ctx = face.assemblyContext if face else None
        except Exception:
            ctx = None
        if ctx:
            occs.append(ctx)
    return occs


def _highlight_candidate(inputs, cand):
    """Highlight the candidate's component pair (or ground component) in the
    graphics via the preview SelectionCommandInput (which highlights even while
    the command dialog is open, unlike ui.activeSelections)."""
    sel = adsk.core.SelectionCommandInput.cast(inputs.itemById(PREVIEW_SEL_ID))
    if not sel:
        return
    sel.clearSelection()
    if not cand:
        return
    for occ in _candidate_occurrences(cand):
        try:
            sel.addSelection(occ)
        except Exception as sel_err:
            futil.log(f"{CMD_NAME}: could not highlight ({sel_err})")


def _highlight_selected_row(inputs, table):
    """Highlight the component pair for the currently-selected table row."""
    if not table:
        return
    cand = next((c for c in _candidates if c.get("row") == table.selectedRow), None)
    _highlight_candidate(inputs, cand)


def command_execute(args: adsk.core.CommandEventArgs):
    futil.log(f"{CMD_NAME} Command Execute Event")

    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        ui.messageBox("A Fusion 3D Design must be active.", CMD_NAME)
        return

    inputs = args.command.commandInputs
    selected = []
    for cand in _candidates:
        chk = adsk.core.BoolValueCommandInput.cast(inputs.itemById(cand["chk_id"]))
        if chk and chk.value:
            # Capture the user's joint-type choice for joint (centered) rows.
            if cand.get("centered") and cand.get("joint_dd_id"):
                dd = adsk.core.DropDownCommandInput.cast(
                    inputs.itemById(cand["joint_dd_id"])
                )
                item = dd.selectedItem if dd else None
                cand["motion"] = item.name if item else DEFAULT_JOINT_TYPE
            selected.append(cand)

    if not selected:
        ui.messageBox("No relationships were selected to apply.", CMD_NAME)
        return

    root = design.rootComponent

    # Capture the current pose first so the constraint solve cannot drift the
    # assembly (API equivalent of "Capture Position").
    try:
        snaps = design.snapshots
        if snaps and snaps.hasPendingTransforms:
            snaps.add()
    except Exception as snap_err:
        futil.log(f"{CMD_NAME}: snapshot skipped ({snap_err})")

    created = 0
    failed = 0
    redundant = 0
    moved = 0
    max_move_mm = 0.0
    # Greedy, DOF-aware acceptance (CAD-Mate-Inference Part 2 A.4): apply each
    # candidate, then ask Fusion's own solver whether it is over-constrained
    # (a sick healthState). A sick constraint adds no independent DOF reduction
    # - it closes a cycle in the component graph - so we drop it. This keeps the
    # maximal non-redundant set without computing the constraint Jacobian
    # ourselves. Candidates are processed in confidence order so the strongest
    # relationships seed the spanning structure first.
    for cand in selected:
        try:
            con = _apply_candidate(root, cand)
            if con is not None and _is_sick(con):
                con.deleteMe()
                redundant += 1
                continue
            created += 1
            move_mm = cand.get("applied_move_cm", 0.0) * 10.0
            if move_mm > POS_TOL_CM * 10.0:
                moved += 1
                max_move_mm = max(max_move_mm, move_mm)
        except Exception as apply_err:
            failed += 1
            futil.log(
                f"{CMD_NAME}: failed to apply {cand['type']} "
                f"{cand['label']}: {apply_err}"
            )

    msg = f"Applied {created} relationship(s)."
    if redundant:
        msg += (
            f"\nSkipped {redundant} redundant constraint(s) that would have "
            "over-constrained the assembly (they closed a cycle already covered "
            "by stronger relationships)."
        )
    if moved:
        msg += (
            f"\n{moved} repositioned a component (up to {max_move_mm:.2f} mm); "
            "review and undo if unwanted."
        )
    if failed:
        msg += (
            f"\n{failed} could not be created (see the Text Command window for "
            "details). The Assembly Constraints API is a Fusion preview feature "
            "and may not be available in this build."
        )
    ui.messageBox(msg, CMD_NAME)


def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers, _candidates
    local_handlers = []
    _candidates = []


# ---------------------------------------------------------------------------
# Dialog helpers
# ---------------------------------------------------------------------------
def _add_header_row(inputs, table):
    for col, label in enumerate(["Apply", "Type", "Components", "Conf."]):
        hdr = inputs.addStringValueInput(f"ic_hdr_{col}", "", label)
        hdr.isReadOnly = True
        table.addCommandInput(hdr, HEADER_ROW, col)


def _rescan(design, inputs):
    """Run detection with the current tolerances and rebuild the preview table."""
    global _candidates

    lin_tol = DEFAULT_LIN_TOL_CM
    ang_tol = DEFAULT_ANG_TOL_RAD
    lin_in = inputs.itemById(LIN_TOL_ID)
    ang_in = inputs.itemById(ANG_TOL_ID)
    if lin_in and lin_in.value > 0:
        lin_tol = lin_in.value
    if ang_in and ang_in.value > 0:
        ang_tol = ang_in.value

    _candidates, stats = _infer(design, lin_tol, ang_tol)

    table = adsk.core.TableCommandInput.cast(inputs.itemById(TABLE_ID))
    # Remove existing data rows but keep the header row.  Data-row inputs use a
    # monotonic id counter so rebuilt rows never collide with prior ones.
    while table.rowCount > HEADER_ROW + 1:
        table.deleteRow(table.rowCount - 1)
    for cand in _candidates:
        _add_candidate_row(inputs, table, cand)

    checked = sum(1 for c in _candidates if c["default_checked"])
    summary = inputs.itemById(SUMMARY_ID)
    if summary:
        diag = (
            f"Scanned {stats['occurrences']} occurrence(s) + "
            f"{stats['root_bodies']} root body(ies): {stats['faces']} analytic "
            f"faces ({stats['planar']} planar, {stats['cylindrical']} "
            f"cylindrical), {stats['pairs_tested']} pair(s) tested.\n"
        )
        if stats["faces"] == 0:
            diag += (
                "No planar or cylindrical faces found - this command needs "
                "component occurrences or solid bodies with analytic faces."
            )
        elif not _candidates:
            diag += (
                "No matches at the current tolerances. Try increasing the "
                "linear/angular tolerance and Re-scan."
            )
        else:
            diag += f"{len(_candidates)} relationship(s) found, {checked} selected."
        summary.text = diag


def _add_candidate_row(inputs, table, cand):
    global _row_counter
    _row_counter += 1
    rid = _row_counter
    row = table.rowCount
    cand["row"] = row  # for mapping a selected table row back to its candidate

    chk_id = f"ic_chk_{rid}"
    chk = inputs.addBoolValueInput(chk_id, "", True, "", cand["default_checked"])
    cand["chk_id"] = chk_id

    # Joint rows (centered coincident) get a joint-type dropdown in the Type
    # column so the user can pick Rigid / Revolute / Cylindrical / ... ; other
    # rows show static relationship text.
    if cand.get("centered"):
        dd_id = f"ic_jt_{rid}"
        dd = inputs.addDropDownCommandInput(
            dd_id, "", adsk.core.DropDownStyles.LabeledIconDropDownStyle
        )
        for label, folder in JOINT_TYPES:
            dd.listItems.add(
                label,
                label == DEFAULT_JOINT_TYPE,
                os.path.join(JOINTS_ICON_DIR, folder),
            )
        cand["joint_dd_id"] = dd_id
        type_cell = dd
    else:
        type_cell = inputs.addStringValueInput(f"ic_type_{rid}", "", cand["type"])
        type_cell.isReadOnly = True

    # Components cell is a momentary button; clicking it highlights this pair in
    # the graphics. Works uniformly for joint and constraint rows (clicking a
    # bare table row does not fire an event in Fusion).
    comp_btn_id = f"ic_comp_{rid}"
    comp_in = inputs.addBoolValueInput(comp_btn_id, cand["label"], False)
    comp_in.tooltip = "Click to highlight these components in the graphics"
    cand["comp_btn_id"] = comp_btn_id

    conf_in = inputs.addStringValueInput(
        f"ic_conf_{rid}", "", f"{cand['confidence']:.2f}"
    )
    conf_in.isReadOnly = True

    table.addCommandInput(chk, row, 0)
    table.addCommandInput(type_cell, row, 1)
    table.addCommandInput(comp_in, row, 2)
    table.addCommandInput(conf_in, row, 3)


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------
class _FaceRec:
    """An analytic face captured in root (world) space.

    *src* identifies the part the face belongs to (an occurrence path, or a
    root body) so faces on the same part are never paired with each other;
    *name* is the human-readable label shown in the preview table.
    """

    __slots__ = (
        "src",
        "name",
        "ftype",
        "origin",
        "dir",
        "radius",
        "area",
        "bbox",
        "face",
    )

    def __init__(self, src, name, ftype, origin, direction, radius, face):
        self.src = src
        self.name = name
        self.ftype = ftype
        self.origin = origin
        self.dir = direction
        self.radius = radius
        self.area = face.area
        self.bbox = face.boundingBox
        self.face = face


def _unit(vec):
    v = vec.copy()
    v.normalize()
    return v


def _add_body_faces(records, body, src, name):
    """Append planar/cylindrical face records for one solid body."""
    if not body.isSolid:
        return
    for face in body.faces:
        try:
            geom = face.geometry
            cyl = adsk.core.Cylinder.cast(geom)
            if cyl:
                records.append(
                    _FaceRec(src, name, "cyl", cyl.origin, _unit(cyl.axis),
                             cyl.radius, face)
                )
                continue
            plane = adsk.core.Plane.cast(geom)
            if plane:
                records.append(
                    _FaceRec(src, name, "plane", plane.origin,
                             _unit(plane.normal), None, face)
                )
        except Exception as face_err:
            futil.log(f"{CMD_NAME}: skipped a face ({face_err})")


def _collect_faces(design):
    """Collect planar and cylindrical analytic faces.

    Scans both component occurrences (the normal assembly case) and bodies that
    live directly in the root component (e.g. a STEP that imports as bodies, or
    a multi-body design). Occurrence body proxies report geometry in the root
    component's coordinate system, so the surface parameters are already in
    world space - no transform math required (CAD-Mate-Inference, Part 2 B.2).

    Returns (records, stats) where stats describes what was scanned.
    """
    records = []
    root = design.rootComponent
    n_occ = 0
    for occ in root.allOccurrences:
        try:
            if occ.childOccurrences.count > 0:
                continue  # leaf occurrences only
            if not occ.isVisible:
                continue  # Occurrence has isVisible/isLightBulbOn, not isSuppressed
            n_occ += 1
            for body in occ.bRepBodies:
                _add_body_faces(records, body, occ.fullPathName, occ.name)
        except Exception as occ_err:
            futil.log(f"{CMD_NAME}: skipped an occurrence ({occ_err})")

    # Root-level bodies (no occurrence). Key each body separately so two
    # different root bodies can pair, but faces on one body cannot.
    n_root_bodies = 0
    for bi in range(root.bRepBodies.count):
        try:
            body = root.bRepBodies.item(bi)
            if not body.isSolid:
                continue
            n_root_bodies += 1
            _add_body_faces(records, body, f"root::body::{bi}", body.name)
        except Exception as body_err:
            futil.log(f"{CMD_NAME}: skipped a root body ({body_err})")

    planar = sum(1 for r in records if r.ftype == "plane")
    cyl = sum(1 for r in records if r.ftype == "cyl")
    stats = {
        "occurrences": n_occ,
        "root_bodies": n_root_bodies,
        "faces": len(records),
        "planar": planar,
        "cylindrical": cyl,
        "pairs_tested": 0,
    }
    return records, stats


def _bbox_near(b1, b2, tol):
    return (
        b1.minPoint.x - tol <= b2.maxPoint.x
        and b2.minPoint.x - tol <= b1.maxPoint.x
        and b1.minPoint.y - tol <= b2.maxPoint.y
        and b2.minPoint.y - tol <= b1.maxPoint.y
        and b1.minPoint.z - tol <= b2.maxPoint.z
        and b2.minPoint.z - tol <= b1.maxPoint.z
    )


def _clamp01(x):
    return max(0.0, min(1.0, x))


def _candidate_strength(c):
    """How strongly a candidate constrains, used to order apply strongest-first.
    Higher = applied earlier so it stays healthy and weaker redundant ones drop."""
    if c.get("centered"):
        return 3  # centered coincident -> rigid joint (fully locks the pair)
    if c["type"] == "Concentric":
        return 2  # coaxial -> removes 4 DOF
    return 1  # coincident plane -> removes 3 DOF


def _infer(design, lin_tol, ang_tol):
    """Return (candidates, stats): a ranked, de-duplicated candidate list and
    a dict describing what was scanned (for the diagnostic summary)."""
    faces, stats = _collect_faces(design)
    if len(faces) > FACE_WARN_COUNT:
        futil.log(
            f"{CMD_NAME}: {len(faces)} analytic faces - broad phase is O(n^2) "
            "and may be slow."
        )

    sin_ang = math.sin(ang_tol)
    # Best candidate per (part-pair, type), keyed so redundant face pairs
    # between the same two parts collapse to the strongest one.
    best = {}

    pairs_tested = 0
    n = len(faces)
    for i in range(n):
        a = faces[i]
        for j in range(i + 1, n):
            b = faces[j]
            if a.src == b.src:
                continue  # faces on the same part
            if a.ftype != b.ftype:
                continue
            if not _bbox_near(a.bbox, b.bbox, lin_tol):
                continue

            pairs_tested += 1
            if a.ftype == "cyl":
                cand = _test_concentric(a, b, lin_tol, sin_ang)
            else:
                cand = _test_coincident(a, b, lin_tol, sin_ang)
            if cand is None:
                continue

            key = (tuple(sorted((a.src, b.src))), cand["type"])
            if key not in best or cand["confidence"] > best[key]["confidence"]:
                best[key] = cand

    stats["pairs_tested"] = pairs_tested
    # Order strongest-first so the most-constraining relationships seed the
    # solution before weaker ones. This is critical: a rigid joint applied AFTER
    # a concentric constraint on the same parts comes out over-constrained
    # (sick) and gets dropped, leaving the pair under-constrained. Applying the
    # rigid joints first keeps them healthy; the now-redundant constraints drop
    # instead. Ties broken by confidence.
    candidates = sorted(
        best.values(),
        key=lambda c: (_candidate_strength(c), c["confidence"]),
        reverse=True,
    )
    for c in candidates:
        c["default_checked"] = c["confidence"] >= AUTO_CHECK_CONF

    # Special case: the very first entry grounds the first browser component to
    # its parent, giving the solver a fixed reference for everything else.
    ground = _ground_candidate(design)
    if ground:
        candidates.insert(0, ground)
    return candidates, stats


def _first_browser_occurrence(design):
    """The first top-level component as shown in the browser.

    root.occurrences is in an internal order that does NOT match the browser, so
    in a parametric design we use the timeline (the first occurrence-creation
    entity = the browser-top component). Direct designs have no timeline, so we
    fall back to root.occurrences order there.
    """
    root = design.rootComponent
    try:
        if design.designType == adsk.fusion.DesignTypes.ParametricDesignType:
            tl = design.timeline
            for i in range(tl.count):
                try:
                    ent = tl.item(i).entity
                except Exception:
                    ent = None
                occ = adsk.fusion.Occurrence.cast(ent)
                # Only a top-level occurrence (direct child of the root).
                if occ and occ.assemblyContext is None:
                    return occ
    except Exception:
        pass
    occs = root.occurrences
    return occs.item(0) if occs.count else None


def _ground_candidate(design):
    """A 'Ground to Parent' relationship on the first component in the browser.
    None if there is no top-level component to ground."""
    occ = _first_browser_occurrence(design)
    if occ is None:
        return None
    return {
        "type": "Ground",
        "detail": "ground to parent",
        "label": f"{occ.name} (ground to parent)",
        "confidence": 1.0,
        "occ": occ,
        "default_checked": True,
    }


def _test_concentric(a, b, lin_tol, sin_ang):
    """Two cylindrical faces sharing a common axis (shaft-in-hole allowed)."""
    axis_cross = a.dir.crossProduct(b.dir).length
    if axis_cross > sin_ang:
        return None
    # Perpendicular distance between the two axes (a.dir is unit).
    between = a.origin.vectorTo(b.origin)
    axis_off = between.crossProduct(a.dir).length
    if axis_off > lin_tol:
        return None

    ang_score = 1.0 - axis_cross / sin_ang if sin_ang > 0 else 1.0
    off_score = 1.0 - axis_off / lin_tol if lin_tol > 0 else 1.0
    confidence = _clamp01(0.5 * ang_score + 0.5 * off_score)

    clearance = abs(a.radius - b.radius)
    detail = "shaft-in-hole" if clearance > lin_tol else "equal radius"
    return {
        "type": "Concentric",
        "detail": detail,
        "label": f"{a.name} ↔ {b.name}",
        "confidence": confidence,
        "face_a": a.face,
        "face_b": b.face,
        # Coaxial faces are already aligned in the current pose; no offset and
        # axes share a sense, so they are not flipped.  VERIFY AT RUNTIME.
        "is_mate": True,
        "is_flipped": False,
        "offset_cm": 0.0,
    }


def _test_coincident(a, b, lin_tol, sin_ang):
    """Two planar faces lying flush (parallel, within the linear gap)."""
    normal_cross = a.dir.crossProduct(b.dir).length
    if normal_cross > sin_ang:
        return None
    between = a.origin.vectorTo(b.origin)
    gap = between.dotProduct(a.dir)  # signed distance along A's normal
    if abs(gap) > lin_tol:
        return None

    ang_score = 1.0 - normal_cross / sin_ang if sin_ang > 0 else 1.0
    gap_score = 1.0 - abs(gap) / lin_tol if lin_tol > 0 else 1.0
    confidence = _clamp01(0.5 * ang_score + 0.5 * gap_score)

    # Special case: if the two face centroids coincide as well, the faces are
    # centered on each other - a rigid joint pinned at the shared centroid fully
    # locates them with no jump (verified). Otherwise a coincident assembly
    # constraint (which leaves the in-plane DOF free) is the right relationship.
    try:
        centered = a.face.centroid.distanceTo(b.face.centroid) <= lin_tol
    except Exception:
        centered = False

    opposed = a.dir.dotProduct(b.dir) < 0.0
    return {
        "type": "Coincident",
        "detail": "centered (rigid)" if centered else "flush faces",
        "label": f"{a.name} ↔ {b.name}",
        "confidence": confidence,
        "face_a": a.face,
        "face_b": b.face,
        "is_mate": True,
        "is_flipped": opposed,
        "offset_cm": gap,
        "centered": centered,
    }


# ---------------------------------------------------------------------------
# Apply (Fusion preview Assembly Constraints API)
# ---------------------------------------------------------------------------
# Movement (cm) below which an applied constraint is considered position-
# preserving (no visible jump).
POS_TOL_CM = 1.0e-3


def _is_sick(constraint):
    """True only if Fusion flags the constraint as over-constrained or
    unsatisfiable, i.e. Warning or Error health.

    Do NOT treat every non-Healthy state as sick: in a *direct* (non-parametric)
    design there is no timeline, so a perfectly valid constraint reports
    Unknown (not Healthy). Suppressed/RolledBack/Unknown are not failures - only
    Warning/Error are. Reading errorOrWarningMessage can itself raise, so we key
    off the state enum only.
    """
    try:
        hs = constraint.healthState
        return hs in (
            adsk.fusion.FeatureHealthStates.WarningFeatureHealthState,
            adsk.fusion.FeatureHealthStates.ErrorFeatureHealthState,
        )
    except Exception:
        return False


def _moving_occurrences(face_a, face_b):
    occs = []
    for f in (face_a, face_b):
        try:
            ctx = f.assemblyContext
        except Exception:
            ctx = None
        if ctx and all(ctx.entityToken != o.entityToken for o in occs):
            occs.append(ctx)
    return occs


def _probe_radius_cm(occ):
    """A length (cm) representative of the occurrence's size, used so that a
    rotation is registered as movement proportional to the part's extent."""
    try:
        bb = occ.boundingBox
        dx = bb.maxPoint.x - bb.minPoint.x
        dy = bb.maxPoint.y - bb.minPoint.y
        dz = bb.maxPoint.z - bb.minPoint.z
        r = 0.5 * math.sqrt(dx * dx + dy * dy + dz * dz)
        return r if r > 1.0e-6 else 1.0
    except Exception:
        return 1.0


def _max_move_cm(saved):
    """Largest displacement (cm) of any tracked occurrence vs its saved pose.

    Measures rigid motion (translation AND rotation) by transforming a small
    set of probe points - the origin plus three points at the part's radius -
    by the before/after matrices and taking the worst point displacement. This
    catches a part that rotates about its own axis, which a pure
    origin-translation check would miss.
    """
    worst = 0.0
    for occ, before in saved:
        after = occ.transform2
        r = _probe_radius_cm(occ)
        for px, py, pz in ((0.0, 0.0, 0.0), (r, 0.0, 0.0), (0.0, r, 0.0), (0.0, 0.0, r)):
            pb = adsk.core.Point3D.create(px, py, pz)
            pb.transformBy(before)
            pa = adsk.core.Point3D.create(px, py, pz)
            pa.transformBy(after)
            d = math.sqrt(
                (pa.x - pb.x) ** 2 + (pa.y - pb.y) ** 2 + (pa.z - pb.z) ** 2
            )
            worst = max(worst, d)
    return worst


def _create_constraint(constraints, face_a, face_b, is_mate, offset_cm, flip):
    cin = constraints.createInput()
    rel = cin.geometricRelationships.add(
        face_a, face_b, is_mate, adsk.core.ValueInput.createByReal(offset_cm)
    )
    try:
        rel.isFlipped = flip
    except Exception as flip_err:
        futil.log(f"{CMD_NAME}: could not set isFlipped ({flip_err})")
    return constraints.add(cin)


def _restore(saved):
    for occ, before in saved:
        try:
            occ.transform2 = before
        except Exception as restore_err:
            futil.log(f"{CMD_NAME}: could not restore position ({restore_err})")


def _make_planar_center_geometry(face):
    return adsk.fusion.JointGeometry.createByPlanarFace(
        face, None, adsk.fusion.JointKeyPointTypes.CenterKeyPoint
    )


def _set_joint_motion(jin, motion):
    """Apply the chosen motion to a JointInput. For a planar-face joint the
    primary axis is the face normal (Z), so non-rigid motions act about/along
    that axis. Defaults to rigid for any unrecognized value."""
    JD = adsk.fusion.JointDirections
    z = JD.ZAxisJointDirection
    x = JD.XAxisJointDirection
    if motion == "Revolute":
        jin.setAsRevoluteJointMotion(z)
    elif motion == "Slider":
        jin.setAsSliderJointMotion(z)
    elif motion == "Cylindrical":
        jin.setAsCylindricalJointMotion(z)
    elif motion == "Pin-Slot":
        jin.setAsPinSlotJointMotion(z, x)
    elif motion == "Planar":
        jin.setAsPlanarJointMotion(z)
    elif motion == "Ball":
        jin.setAsBallJointMotion(z, x)
    else:
        jin.setAsRigidJointMotion()


def _create_joint(joints, face_a, face_b, flip, motion):
    # Fresh JointGeometry per createInput - it is consumed by the input.
    jin = joints.createInput(
        _make_planar_center_geometry(face_a), _make_planar_center_geometry(face_b)
    )
    try:
        jin.isFlipped = flip
    except Exception as flip_err:
        futil.log(f"{CMD_NAME}: could not set joint isFlipped ({flip_err})")
    _set_joint_motion(jin, motion)
    return joints.add(jin)


def _apply_rigid_centered_joint(root, cand):
    """Centered-coincident special case: a Joint with both inputs on the faces'
    center keypoints, using the motion type the user picked (default Rigid).
    Because the centroids already coincide this is position-preserving; the flip
    that preserves position is chosen by trial as for constraints."""
    joints = root.joints
    fa, fb = cand["face_a"], cand["face_b"]
    motion = cand.get("motion", DEFAULT_JOINT_TYPE)
    occs = _moving_occurrences(fa, fb)

    best = None  # (move, flip)
    for flip in (False, True):
        saved = [(o, o.transform2.copy()) for o in occs]
        jt = _create_joint(joints, fa, fb, flip, motion)
        move = _max_move_cm(saved)
        if best is None or move < best[0]:
            best = (move, flip)
        jt.deleteMe()
        _restore(saved)
        if move <= POS_TOL_CM:
            break

    flip = best[1]
    saved = [(o, o.transform2.copy()) for o in occs]
    jt = _create_joint(joints, fa, fb, flip, motion)
    cand["applied_move_cm"] = _max_move_cm(saved)
    return jt


def _apply_candidate(root: adsk.fusion.Component, cand: dict):
    """Create one position-preserving assembly constraint from a candidate.

    Real preview-API call shape (verified at runtime against Fusion's live
    build; the published docs were incomplete):

        cin = constraints.createInput()
        rel = cin.geometricRelationships.add(entityOne, entityTwo, isMate,
                                             offsetOrAngleValue)
        rel.isFlipped = ...
        constraints.add(cin)

    The offset sign and isFlipped that keep the parts from jumping are NOT
    reliably derivable from face-normal orientation, so we try the small set of
    variants, measure how far the affected occurrences move, and keep the one
    that preserves position (or moves least). For coincident faces this reaches
    zero movement; a single cylinder mate cannot encode the free rotation, so
    concentric keeps the least-moving variant and reports the residual.

    The "Ground" special case grounds the candidate's occurrence to its parent
    instead of creating an assembly constraint, and returns None. The centered
    coincident special case creates a Rigid Joint at the shared face centroid.
    """
    if cand["type"] == "Ground":
        cand["occ"].isGroundToParent = True
        cand["applied_move_cm"] = 0.0
        return None

    if cand.get("centered"):
        return _apply_rigid_centered_joint(root, cand)

    constraints = root.assemblyConstraints
    fa, fb = cand["face_a"], cand["face_b"]
    is_mate = cand.get("is_mate", True)
    occs = _moving_occurrences(fa, fb)

    base_offset = cand.get("offset_cm", 0.0) or 0.0
    if cand["type"] == "Coincident":
        offsets = [base_offset]
    else:
        offsets = [0.0]

    best = None  # (move, offset, flip)
    for off in offsets:
        for flip in (False, True):
            saved = [(o, o.transform2.copy()) for o in occs]
            con = _create_constraint(constraints, fa, fb, is_mate, off, flip)
            move = _max_move_cm(saved)
            if best is None or move < best[0]:
                best = (move, off, flip)
            con.deleteMe()
            _restore(saved)
            if move <= POS_TOL_CM:
                break
        if best and best[0] <= POS_TOL_CM:
            break

    move, off, flip = best
    saved = [(o, o.transform2.copy()) for o in occs]
    con = _create_constraint(constraints, fa, fb, is_mate, off, flip)
    cand["applied_move_cm"] = _max_move_cm(saved)
    return con
