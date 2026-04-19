# PowerTools: Assembly tools for Autodesk Fusion

PowerTools Assembly is an Autodesk Fusion add-in that provides productivity commands for teams working with multi-component assemblies and cloud-connected design data. It adds commands to the Design workspace toolbar and Quick Access Toolbar (QAT) that reduce the steps required for common assembly management tasks.

## Prerequisites

Before you install and run this add-in, confirm that you have the following:

- **Autodesk Fusion** (any current subscription tier) with Python add-in support enabled
- **Windows 10/11** or **macOS**
- An **Autodesk Team Hub** (required for commands that access cloud document references)

## Installation

1. Download or clone this repository to your local machine.
2. In Autodesk Fusion, open the **Add-Ins** dialog by selecting **Utilities** > **Add-Ins**, or press **Shift+S**.
3. On the **Add-Ins** tab, click the green **+** icon.
4. Navigate to the folder where you placed the add-in files and select the `PowerTools-Assembly` folder.
5. Click **Open**.
6. Select **PowerTools Assembly** in the list, then click **Run**.

To have the add-in load automatically each time Fusion starts, select **Run on Startup** before clicking **Run**.

## Commands

The following commands are included in this add-in:

| Command | Category | Location | Description |
|---|---|---|---|
| [Document References](./docs/Document%20References.md) | Data Workflow | Design &rsaquo; Utilities &rsaquo; Tools | Displays a dialog listing all documents related to the active design, organized by relationship type, including recursive root assembly detection. |
| [Reference Manager](./docs/Reference%20Manager.md) | Data Workflow | Quick Access Toolbar | Opens the Fusion Reference Manager dialog directly from the QAT for quick access to reference management. |
| [Externalize](./docs/Externalize.md) | Data Workflow | Design &rsaquo; PowerTools Assembly panel | Converts local (inline) components into independent cloud documents and re-inserts them at their original positions. |
| [Get and Update](./docs/Get%20and%20Update.md) | Data Workflow | Quick Access Toolbar | Retrieves the latest versions of all child references and updates all out-of-date assembly contexts in one step. |
| [Document Refresh](./docs/Document%20Refresh.md) | Data Workflow | QAT &rsaquo; File dropdown | Closes and reopens the active document to load the latest version from the Hub. |
| [Bottom-Up Update](./docs/Bottom-Up%20Update.md) | Data Workflow | Design &rsaquo; PowerTools Assembly panel | Saves and updates all references in the open assembly from the bottom up, processing components in dependency order. |
| [Assembly Statistics](./docs/Assembly%20Statistics.md) | Information | Design &rsaquo; Utilities &rsaquo; Tools | Displays a summary dialog of component counts, reference states, joints, and assembly nesting depth. |
| [Assembly Builder](./docs/Assembly%20Builder.md) | Productivity | Design &rsaquo; PowerTools Assembly panel | Visual node editor for designing an assembly hierarchy on a new, empty document, then generating every external component with the correct design intent in one step. |
| [Insert STEP File](./docs/Insert%20Step.md) | Productivity | Design &rsaquo; PowerTools Assembly panel | Opens a local file browser and inserts a STEP or F3D file as an inline component in the active design. |
| [Global Parameters](./docs/Global%20Parameters.md) | Global Parameters | Design &rsaquo; PowerTools Assembly panel | Create or edit a shared parameter set document in the active project's `_Global Parameters` folder; writes favorite parameters into the active document. |
| [Link Global Parameters](./docs/Link%20Global%20Parameters.md) | Global Parameters | Design &rsaquo; PowerTools Assembly panel | Derive a parameter set from the project's `_Global Parameters` folder into the active document as a Derive feature with favorite parameters. |
| [Refresh Global Parameters Cache](./docs/Refresh%20Global%20Parameters%20Cache.md) | Global Parameters | QAT &rsaquo; File &rsaquo; PowerTools Settings | Force a full Hub scan and rewrite the local `gp_folder` / `gp_docs` caches for the active project when parameter sets appear missing or stale. |

---

## Data Workflow commands

### Document References

**[Document References](./docs/Document%20References.md)** displays a dialog listing all documents related to the active design — including parents, children, drawings, fasteners, and (when using the Related Data add-in) documents created from templates. You can open any listed document directly by selecting the open button next to its name.

- **Roots** — recursively walks the full parent chain to identify top-level root assemblies that have no further parents; deduplicates by file ID, excludes drawings and Related Data documents from the chain, and excludes the active document itself.
- Thumbnail previews, Open in Fusion, and Open in Browser buttons are available for every section including Roots.

**Requirements:** An Autodesk Fusion 3D Design must be active and saved.

For full usage details, see [Document References](./docs/Document%20References.md).

### Reference Manager

**[Reference Manager](./docs/Reference%20Manager.md)** opens the Fusion Reference Manager dialog directly from the Quick Access Toolbar. Provides a single location to review all references, update them individually or all at once, select specific versions, and open referenced documents in new tabs.

**Requirements:** An Autodesk Fusion 3D Design must be active.

For full usage details, see [Reference Manager](./docs/Reference%20Manager.md).

### Externalize

**[Externalize](./docs/Externalize.md)** converts one or more local (inline) components in the active assembly into independent cloud documents, then re-inserts them at their original positions and orientations.

- Externalize a single selected component occurrence.
- Externalize all local first-level components in one step using **Externalize All**.
- Save to the same folder as the active document or to a new named sub-folder.
- Automatically reuse an existing cloud file if one with the same name already exists.

**Requirements:** An Autodesk Fusion 3D Design must be active and saved.

For full usage details, see [Externalize](./docs/Externalize.md).

### Get and Update

**[Get and Update](./docs/Get%20and%20Update.md)** retrieves the latest versions of all child references and immediately updates all out-of-date assembly contexts in a single operation. Use this command instead of the default **Get Latest** button when you need to ensure that both document versions and their derived assembly contexts are current.

**Requirements:** An Autodesk Fusion 3D Design with external references must be active.

For full usage details, see [Get and Update](./docs/Get%20and%20Update.md).

### Document Refresh

**[Document Refresh](./docs/Document%20Refresh.md)** closes the active document, retrieves the latest version from the Autodesk Hub, and reopens it automatically. Use this command when working in a team to load changes saved by other team members without manually closing and reopening the file.

**Requirements:** An Autodesk Fusion 3D Design must be active and saved.

For full usage details, see [Document Refresh](./docs/Document%20Refresh.md).

### Bottom-Up Update

**[Bottom-Up Update](./docs/Bottom-Up%20Update.md)** saves and updates all references in the open assembly from the bottom up, processing assembly components in dependency order to ensure proper reference updates.

- Updates components from dependencies upward through the assembly hierarchy.
- Optional rebuild of all components to ensure they are current.
- Skips standard library components and already processed documents.
- Applies appropriate design intent (Part, Assembly, or Hybrid) automatically.
- Hides various UI elements (origins, joints, sketches, canvases) for cleaner saves.
- **Smart upload confirmation** — waits for each component's cloud upload to finish before advancing, instead of using a fixed pause timer.
- **Resume-aware** — on launch, inspects the temp log to detect an incomplete prior run; if the component list is unchanged it offers to resume from the last confirmed checkpoint.
- **Live log viewer** — optionally opens Console.app (macOS) or a PowerShell window (Windows) automatically when the command starts so you can monitor progress live.
- Writes structured checkpoint log entries to the OS temp folder for diagnostics and resume support.

**Requirements:** An Autodesk Fusion 3D Design with external references must be active and saved.

For full usage details, see [Bottom-Up Update](./docs/Bottom-Up%20Update.md).

---

## Information commands

### Assembly Statistics

**[Assembly Statistics](./docs/Assembly%20Statistics.md)** displays a summary dialog for the active design showing component instance counts, unique component counts, out-of-date reference counts, assembly nesting depth, document context count, assembly constraints, and joint totals broken down by type.

**Requirements:** An Autodesk Fusion 3D Design must be active.

For full usage details, see [Assembly Statistics](./docs/Assembly%20Statistics.md).

---

## Productivity commands

### Assembly Builder

**[Assembly Builder](./docs/Assembly%20Builder.md)** opens a visual node editor (powered by [Drawflow](https://github.com/jerosoler/Drawflow)) that lets you plan an assembly hierarchy before any components exist, then generates every external component in one step with the correct design intent applied automatically.

- Add **Assembly**, **Part**, and **Hybrid** nodes by clicking them in the sidebar.
- Connect nodes by dragging from parent output ports (bottom) to child input ports (top).
- Share a single child across multiple parents — the command saves once to establish cloud references and then reuses them via `addByInsert`.
- Double-click any node to rename it; the name is applied to the generated Fusion component.
- Built-in zoom, pan, and fit-to-view controls; palette theme follows the Fusion UI theme.

**Requirements:** An active Fusion 3D Design that is new and unsaved, has Assembly or Hybrid design intent, and has no root-level children.

For full usage details, see [Assembly Builder](./docs/Assembly%20Builder.md).

### Insert STEP File

**[Insert STEP File](./docs/Insert%20Step.md)** opens a local file browser and inserts a selected STEP (`.stp`, `.step`) or Fusion archive (`.f3d`) file as an inline component in the active design. Bypasses the Hub upload and separate-tab workflow for faster local STEP insertion. Particularly useful in ECAD workflows for loading mechanical models into 3D package design tools.

**Requirements:** An Autodesk Fusion 3D Design must be active.

For full usage details, see [Insert STEP File](./docs/Insert%20Step.md).

---

## Global Parameters commands

These commands let teams define and distribute shared design parameters (material thicknesses, clearances, standard dimensions, etc.) across an entire Autodesk Hub project. Parameter sets are stored as Fusion design documents inside a `_Global Parameters` folder at the project root — the underscore prefix causes the folder to sort to the top of the Data Panel. Every parameter is marked as a Fusion **favorite** and tagged with the `PT-globparm` sentinel in its comment so the add-in can identify it across documents.

Both dialogs use a two-level cache (`gp_folder_<project-key>.json` and `gp_docs_<project-key>.json` under `cache/`) so repeat openings skip the Hub folder scan. When a cache read fails, the command falls back to a Hub scan and refreshes the cache automatically. See **Refresh Global Parameters Cache** to force a full rescan.

### Global Parameters

**[Global Parameters](./docs/Global%20Parameters.md)** opens a dialog where you create or edit a named parameter set document in the active project's `_Global Parameters` folder. Parameters defined in the table are written as `userParameter`s (marked `isFavorite = True`) into both the parameter set document and the active document.

- Create a new named parameter set, or edit an existing one chosen from the dropdown.
- Define parameters with a name, numeric value, unit (in, ft, mm, cm, m), and optional comment.
- Parameter names are validated against a regex and a Fusion reserved-unit list; duplicates are rejected with an inline reason.
- Unsaved dialog state is cached on cancel and can be restored on next open.

**Requirements:** An Autodesk Fusion 3D Design must be active and saved to a Hub project.

For full usage details, see [Global Parameters](./docs/Global%20Parameters.md).

### Link Global Parameters

**[Link Global Parameters](./docs/Link%20Global%20Parameters.md)** scans the active project's `_Global Parameters` folder and lets you derive a selected parameter set into the active document as a Derive feature with `isIncludeFavoriteParameters = True`, so every favorite parameter becomes immediately available in design expressions.

- Dropdown of available parameter sets; preview table shows name, expression, unit, and comment before committing.
- Fast preview via JSON sidecar written by **Global Parameters** on save — avoids switching the active document.
- Cache-id fast path for DataFile resolution, with forced Hub refresh fallback when a selected set is unresolved.

**Requirements:** An Autodesk Fusion 3D Design must be active and saved. At least one parameter set must exist in the project.

For full usage details, see [Link Global Parameters](./docs/Link%20Global%20Parameters.md).

### Refresh Global Parameters Cache

**[Refresh Global Parameters Cache](./docs/Refresh%20Global%20Parameters%20Cache.md)** forces a full Hub scan of the active project's `_Global Parameters` folder and overwrites the `gp_folder` and `gp_docs` caches. Use this when parameter sets appear missing, stale, or out of order in the other two dialogs.

- Location: **QAT › File › PowerTools Settings › Refresh Global Parameters Cache**
- The **PowerTools Settings** submenu is shared with other PowerTools add-ins; the command creates it on first run if it does not already exist.

**Requirements:** An active Fusion document whose project contains a `_Global Parameters` folder.

For full usage details, see [Refresh Global Parameters Cache](./docs/Refresh%20Global%20Parameters%20Cache.md).

---

## Support

This add-in is developed and maintained by IMA LLC.

---

## License

This project is released under the [GNU General Public License v3.0 or later](LICENSE).

Copyright (C) 2022-2026 IMA LLC.

The vendored library at `lib/fusionAddInUtils` is Autodesk sample code and is distributed under its own license terms; see its source headers for details.

---

*Copyright © 2026 IMA LLC. All rights reserved.*
