# Assembly Statistics

[Back to PowerTools Assembly](../README.md)

The Assembly Statistics command displays a summary of the structure, component counts, and joint configuration of the active Autodesk Fusion design. Use this command to quickly evaluate the complexity of an assembly without manually inspecting the browser tree.

## What you can do

- View the total number of components in the active assembly, including all nested occurrences.
- View the total number of unique component definitions (local and external).
- View the number of external document references.
- View the number of out-of-date references.
- View the maximum depth (nesting levels) of the assembly hierarchy.
- View the number of document contexts in the timeline.
- View assembly constraints, tangent relationships, and rigid group counts.
- View joint totals broken down by joint type.

## Prerequisites

- A Autodesk Fusion 3D Design must be active.
- The active document must be saved.

## How to use Assembly Statistics

1. Open the Autodesk Fusion Design workspace.
2. On the **Utilities** tab, in the **Tools** panel, select **Assembly Statistics**.
3. Review the statistics displayed in the dialog.
4. Select **Close** to dismiss the dialog.

The dialog reports the following values:

| Statistic | Description |
|---|---|
| Total component instances | Total number of occurrences across all levels of the assembly |
| Unique component definitions | Number of distinct component definitions, excluding the root |
| Out-of-date references | Components whose referenced document has a newer version available |
| Maximum assembly depth | Number of nesting levels from the root to the deepest component |
| Document contexts | Number of assembly context entries in the timeline |
| Assembly constraints | Count of positional constraints on the root component |
| Tangent relationships | Count of tangent relationships on the root component |
| Rigid groups | Count of rigid group constraints on the root component |
| Total joints | All joints defined at the root level |
| Joints by type | Count per joint type (Rigid, Revolute, Slider, Cylindrical, Pin-Slot, Planar, Ball) |

![Assembly Statistics dialog](assets/assemblystats_001.png)

## Access

The **Assembly Statistics** command is located on the **Utilities** tab, in the **Tools** panel of the Autodesk Fusion Design workspace.

![Toolbar access](assets/assemblystats_002.png)

## Architecture

The following diagram shows how the Assembly Statistics command interacts with Autodesk Fusion and its data model.

```mermaid
C4Context
  title Assembly Statistics – System Context

  Person(user, "Design Engineer", "Autodesk Fusion user reviewing assembly structure")
  System(addin, "PowerTools Assembly", "Autodesk Fusion add-in")
  System_Ext(fusion, "Autodesk Fusion", "Host application and Python API (adsk.core / adsk.fusion)")
  System_Ext(hub, "Autodesk Hub", "Cloud document storage and version management")

  Rel(user, addin, "Runs Assembly Statistics")
  Rel(addin, fusion, "Queries component hierarchy, joints, references, and timeline via adsk API and text commands")
  Rel(fusion, hub, "Resolves document references and version state")
```

```mermaid
C4Component
  title Assembly Statistics – Component View

  Person(user, "Design Engineer")
  Component(cmd, "assemblystats/entry.py", "PowerTools Command", "Registers button in Utilities > Tools panel and handles command lifecycle")
  Component(api_design, "adsk.fusion.Design", "Fusion API", "Provides allComponents, rootComponent, assemblyConstraints, joints")
  Component(api_doc, "adsk.core.Application / Document", "Fusion API", "Provides documentReferences and text command execution")
  Component(text_cmd, "Component.AnalyseHierarchy", "Fusion Text Command", "Returns assembly depth and instance hierarchy text output")

  Rel(user, cmd, "Clicks Assembly Statistics button")
  Rel(cmd, api_design, "Reads component counts, joints, and constraints")
  Rel(cmd, api_doc, "Reads out-of-date references and timeline contexts")
  Rel(cmd, text_cmd, "Executes to get hierarchy depth and instance data")
  Rel(cmd, user, "Displays results in modal message dialog")
```

---

[Back to PowerTools Assembly](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
