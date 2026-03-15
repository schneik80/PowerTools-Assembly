# Get and Update

[Back to PowerTools Assembly](../README.md)

The Get and Update command retrieves the latest versions of all child references and then immediately updates all out-of-date assembly contexts in a single operation. Use this command instead of the default Autodesk Fusion **Get Latest** button when you need to ensure that both document versions and their derived assembly contexts are current.

## What you can do

- Retrieve the latest version of all referenced documents with a single click.
- Automatically update all out-of-date assembly contexts immediately after getting the latest versions.
- Replace the two-step (sometimes multi-step) manual process of getting latest and then updating contexts.
- Access the command directly from the Quick Access Toolbar for fast, repeatable use.

## Prerequisites

- A Autodesk Fusion 3D Design with external references must be active.
- The document must be saved to an Autodesk Hub.

## How to use Get and Update

1. On the Quick Access Toolbar (QAT), select the **Get and Update** button.
2. Autodesk Fusion executes **Get All Latest** to download the newest versions of all child references.
3. Autodesk Fusion then executes **Update All Contexts From Parent** to refresh all assembly contexts that depend on the updated references.
4. Review the assembly to confirm references and contexts are current.

> **Tip:** If Autodesk Fusion shows a yellow triangle indicator on the QAT, that signal means at least one child reference has a newer version. Run Get and Update to resolve the indicator and update all derived contexts in one step.

## Access

The **Get and Update** command is located on the Autodesk Fusion **Quick Access Toolbar (QAT)**.

![QAT access](assets/getandupdate.png)

## Architecture

The following diagram shows how the Get and Update command interacts with Autodesk Fusion.

```mermaid
C4Context
  title Get and Update – System Context

  Person(user, "Design Engineer", "Autodesk Fusion user keeping references and contexts current")
  System(addin, "PowerTools Assembly", "Autodesk Fusion add-in")
  System_Ext(fusion, "Autodesk Fusion", "Host application and Python API (adsk.core)")
  System_Ext(hub, "Autodesk Hub", "Cloud document storage and version management")

  Rel(user, addin, "Clicks Get and Update on QAT")
  Rel(addin, fusion, "Executes GetAllLatestCmd then ContextUpdateAllFromParentCmd")
  Rel(fusion, hub, "Downloads latest reference versions")
```

```mermaid
C4Component
  title Get and Update – Component View

  Person(user, "Design Engineer")
  Component(cmd, "getandupdate/entry.py", "PowerTools Command", "Registers QAT button and delegates to built-in Fusion commands")
  Component(get_latest, "GetAllLatestCmd", "Built-in Fusion Command", "Downloads the newest version of every child reference")
  Component(ctx_update, "ContextUpdateAllFromParentCmd", "Built-in Fusion Command", "Refreshes all assembly contexts that are out of date")
  System_Ext(hub, "Autodesk Hub", "Provides latest document versions")

  Rel(user, cmd, "Clicks Get and Update button")
  Rel(cmd, get_latest, "Executes via ui.commandDefinitions")
  Rel(cmd, ctx_update, "Executes via ui.commandDefinitions")
  Rel(get_latest, hub, "Fetches latest reference versions")
```

---

[Back to PowerTools Assembly](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
