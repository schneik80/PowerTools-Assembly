# Reference Manager

[Back to PowerTools Assembly](../README.md)

The Reference Manager command opens the Autodesk Fusion Reference Manager dialog directly from the Quick Access Toolbar. Use this command to review, update, and manage all references in the active document without navigating through nested menus or the Manufacture workspace.

## What you can do

- View all external document references for the active design in one place.
- Update all references to their latest versions in a single action.
- Update individual references selectively, choosing which documents to update.
- Select a specific version for individual references when you need to control which version is used.
- Open any referenced document in a new Autodesk Fusion tab for editing or review.

## Prerequisites

- A Autodesk Fusion 3D Design must be active.
- The document must contain at least one external reference.

## How to use Reference Manager

1. On the Quick Access Toolbar (QAT), select the **Reference Manager** button.
2. The Autodesk Fusion Reference Manager dialog opens, displaying all references in the active document.
3. Use the dialog to perform any of the following actions:

   | Action | How to perform it |
   |---|---|
   | Update all references | Select **Update All** in the dialog |
   | Update one reference | Select the reference row, then select **Update** |
   | Select a specific version | Select the reference row, expand the version list, and choose the desired version |
   | Open a reference | Select the reference row, then select **Open** |

4. Select **OK** or **Close** to dismiss the dialog.

> **Tip:** The Reference Manager is a native Autodesk Fusion tool also available in the Manufacture workspace nesting workflow. This command exposes it in the QAT for quick access from any design session.

## Access

The **Reference Manager** command is located on the Autodesk Fusion **Quick Access Toolbar (QAT)**, positioned next to the **Get and Update** button.

![QAT access](assets/refmanager_002.png)

![Reference Manager dialog](assets/refmanager_001.png)

## Architecture

The following diagram shows how the Reference Manager command interacts with Autodesk Fusion.

```mermaid
C4Context
  title Reference Manager – System Context

  Person(user, "Design Engineer", "Autodesk Fusion user managing document references")
  System(addin, "PowerTools Assembly", "Autodesk Fusion add-in")
  System_Ext(fusion, "Autodesk Fusion", "Host application — provides ReferenceManagerCmd and manages reference versioning")
  System_Ext(hub, "Autodesk Hub", "Cloud document storage and version history")

  Rel(user, addin, "Clicks Reference Manager on QAT")
  Rel(addin, fusion, "Executes built-in ReferenceManagerCmd")
  Rel(fusion, hub, "Reads and writes reference version data")
```

```mermaid
C4Component
  title Reference Manager – Component View

  Person(user, "Design Engineer")
  Component(cmd, "refmanager/entry.py", "PowerTools Command", "Registers QAT button and delegates to the built-in Fusion Reference Manager command")
  Component(ref_mgr_cmd, "ReferenceManagerCmd", "Built-in Fusion Command", "Native Autodesk Fusion reference management dialog with version selection and update capabilities")
  System_Ext(hub, "Autodesk Hub", "Provides reference version history and document metadata")

  Rel(user, cmd, "Clicks Reference Manager on QAT")
  Rel(cmd, ref_mgr_cmd, "Executes via ui.commandDefinitions")
  Rel(ref_mgr_cmd, hub, "Retrieves and updates reference version data")
  Rel(ref_mgr_cmd, user, "Displays Reference Manager dialog")
```

---

[Back to PowerTools Assembly](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
