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
| [Document References](./docs/Document%20References.md) | Data Workflow | Design &rsaquo; Utilities &rsaquo; Tools | Displays a dialog listing all documents related to the active design, organized by relationship type. |
| [Reference Manager](./docs/Reference%20Manager.md) | Data Workflow | Quick Access Toolbar | Opens the Fusion Reference Manager dialog directly from the QAT for quick access to reference management. |
| [Externalize](./docs/Externalize.md) | Data Workflow | Design &rsaquo; PowerTools Assembly panel | Converts local (inline) components into independent cloud documents and re-inserts them at their original positions. |
| [Get and Update](./docs/Get%20and%20Update.md) | Data Workflow | Quick Access Toolbar | Retrieves the latest versions of all child references and updates all out-of-date assembly contexts in one step. |
| [Document Refresh](./docs/Document%20Refresh.md) | Data Workflow | QAT &rsaquo; File dropdown | Closes and reopens the active document to load the latest version from the Hub. |
| [Bottom-Up Update](./docs/Bottom-Up%20Update.md) | Data Workflow | Design &rsaquo; PowerTools Assembly panel | Saves and updates all references in the open assembly from the bottom up, processing components in dependency order. |
| [Assembly Statistics](./docs/Assembly%20Statistics.md) | Information | Design &rsaquo; Utilities &rsaquo; Tools | Displays a summary dialog of component counts, reference states, joints, and assembly nesting depth. |
| [Insert STEP File](./docs/Insert%20Step.md) | Productivity | Design &rsaquo; PowerTools Assembly panel | Opens a local file browser and inserts a STEP or F3D file as an inline component in the active design. |

---

## Data Workflow commands

### Document References

**[Document References](./docs/Document%20References.md)** displays a dialog listing all documents related to the active design — including parents, children, drawings, fasteners, and (when using the Related Data add-in) documents created from templates. You can open any listed document directly by selecting the open button next to its name.

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
- Provides detailed progress logging with timestamps and processing statistics.

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

### Insert STEP File

**[Insert STEP File](./docs/Insert%20Step.md)** opens a local file browser and inserts a selected STEP (`.stp`, `.step`) or Fusion archive (`.f3d`) file as an inline component in the active design. Bypasses the Hub upload and separate-tab workflow for faster local STEP insertion. Particularly useful in ECAD workflows for loading mechanical models into 3D package design tools.

**Requirements:** An Autodesk Fusion 3D Design must be active.

For full usage details, see [Insert STEP File](./docs/Insert%20Step.md).

---

## Support

This add-in is developed and maintained by IMA LLC.

---

## License

This project is released under the [MIT License](LICENSE).

---

*Copyright © 2026 IMA LLC. All rights reserved.*
