# Bottom-Up Update

[Back to PowerTools Assembly](../README.md)

The Bottom-Up Update command traverses the active assembly hierarchy, then opens, updates, and saves each referenced component document in dependency order — from the deepest leaf components upward to the root. This bottom-up sequence ensures that every component's references are current before the components that depend on it are processed.

## What you can do

- Automatically process all components in a complex assembly in correct dependency order.
- Force a complete rebuild of every component to verify they are up to date.
- Apply design document intent (Part, Assembly, or Hybrid) to each component automatically based on its content.
- Hide origins, joints, sketches, joint origins, and canvases before saving to produce cleaner component files.
- Skip standard library components to avoid unnecessary processing overhead.
- Resume a previously interrupted run by skipping components that are already saved.
- Configure a pause interval after each save to allow Autodesk Fusion time between heavy operations.
- Log all processing activity, with timestamps, to a text file for review and audit.

## Prerequisites

Before running the Bottom-Up Update command, confirm the following:

- A Autodesk Fusion 3D Design is active.
- The active document is saved to an Autodesk Hub.
- The active document contains external references to other components.
- You have write access to all component files that will be processed.

## How to use Bottom-Up Update

1. Open the Autodesk Fusion Design workspace with an active saved assembly that contains external references.
2. On the **Utilities** tab, in the **Tools** panel, select **Bottom-up Update**.
3. Configure the options in the three-tab dialog (see [Command options](#command-options) below).
4. Select **OK** to begin processing.
5. Monitor progress in the Autodesk Fusion Text Commands window. Do not interrupt the operation.
6. When the command completes, a summary message confirms the number of components processed and the elapsed time.
7. If logging is enabled, review the log file at the path shown in the completion message.

## Command options

The Bottom-Up Update dialog is organized into three tabs.

### Main tab

| Option | Default | Description |
|---|---|---|
| **Rebuild all** | Enabled | Forces a complete rebuild (`computeAll()`) of each component to ensure it is current. Disable only when you need to preserve the existing computed state. |
| **Skip standard components** | Enabled | Skips Standard Components library documents (such as McMaster-Carr or Misumi parts) to avoid unnecessary processing. |
| **Skip already saved documents** | Disabled | Skips components that were already saved during the current Fusion session. Enable this option to resume a run that was interrupted. |
| **Apply Design Doc Intent** | Disabled | Automatically determines and applies the appropriate Fusion document intent to each component. See [Design intent logic](#design-intent-logic) below. |
| **Pause after save (seconds)** | 4 | Number of seconds to wait after saving each component. Increase this value for large assemblies or slower network storage. Set to 0 to disable pausing. |

### Visibility tab

These options hide specific element types in each component before saving. Each option also configures the corresponding folder visibility so that new elements of that type show or hide correctly in future sessions.

| Option | Default | Effect on folder visibility |
|---|---|---|
| **Hide origins** | Disabled | Hides coordinate system origins. |
| **Hide joints** | Disabled | Hides all joints. Sets the Joints folder to **hidden** so new joints do not appear automatically. |
| **Hide sketches** | Disabled | Hides all sketches. Sets the Sketches folder to **visible** so new sketches appear automatically. |
| **Hide joint origins** | Disabled | Hides all joint origin markers. Sets the Joint Origins folder to **visible** so new joint origins appear automatically. |
| **Hide canvases** | Disabled | Hides all canvases. Sets the Canvases folder to **visible** so new canvases appear automatically. |

### Logging tab

| Option | Default | Description |
|---|---|---|
| **Log Progress** | Enabled | Writes detailed processing events to a plain-text log file (.txt, UTF-8). |
| **Log file path** | Auto-generated | Defaults to `[DocumentName].txt` in the user's Documents folder. Select **Browse…** to choose a different location. |

## Processing sequence

When you select **OK**, the command performs the following steps:

1. **Assembly traversal** — Recursively walks the entire assembly and records all component dependencies as a directed acyclic graph (DAG).
2. **Topological sort** — Sorts the dependency graph in bottom-up order so that leaf components are processed before the assemblies that use them.
3. **Component processing** — For each component in order:
   - Opens the component document.
   - Calls `updateAllReferences()` to bring references up to date.
   - Activates the Fusion Solid Environment workspace.
   - Applies selected visibility options.
   - Applies design intent if enabled.
   - Calls `computeAll()` to rebuild if **Rebuild all** is enabled.
   - Saves the document with a timestamp comment.
   - Closes the component document.
4. **Final assembly update** — Executes **Get All Latest** and **Update All From Parent** on the root assembly, then saves the root document.
5. **Completion report** — Displays a summary with the number of components processed and total elapsed time, and writes the final log entry.

## Design intent logic

When **Apply Design Doc Intent** is enabled, the command analyzes each component and applies one of the following intents:

| Intent | Criteria | Fusion command applied |
|---|---|---|
| **Part** | Component has no child occurrences (leaf node) | `Fusion.setDocumentExperience Part` |
| **Assembly** | Component has child occurrences but no sketches or bodies | `Fusion.setDocumentExperience xrefAssembly` |
| **Hybrid Assembly** | Component has child occurrences AND contains sketches or bodies | `Fusion.setDocumentExperience xrefAssembly hybridAssembly` |

## Log file content

When logging is enabled, the log file records:

- The active document name, project, and document ID.
- The command execution timestamp and all selected options.
- The full bottom-up processing order.
- For each component: open/close events, reference update confirmations, visibility changes, intent application details, rebuild status, and save events with timestamps.
- Any errors or warnings encountered for individual components.
- Final summary statistics: total components processed, total elapsed time, and completion status.

## Best practices

- Save all open documents before running the command.
- Close documents that are not part of the assembly to reduce resource contention.
- Confirm that you have write access to all component files before starting.
- For very large assemblies, consider processing smaller sub-assemblies separately.
- Enable **Log Progress** when troubleshooting to capture detailed error information.
- Use **Skip already saved documents** to resume an interrupted run without reprocessing completed components.

## Troubleshooting

| Symptom | Likely cause | Resolution |
|---|---|---|
| "No document references found" error | Active document has no external references | Confirm you are running the command on an assembly with linked components |
| Component skipped unexpectedly | File is locked or write-protected | Check Hub permissions; ensure no other user has the document open |
| Incomplete processing after interruption | Session interrupted mid-run | Enable **Skip already saved documents** and re-run |
| Design intent not applied | Component is read-only | Ensure the document is not locked; review the log for intent-specific errors |

## Architecture

The following diagrams show how the Bottom-Up Update command fits into the Autodesk Fusion ecosystem and how its internal components interact.

```mermaid
C4Context
  title Bottom-Up Update – System Context

  Person(user, "Design Engineer", "Autodesk Fusion user performing bulk assembly maintenance")
  System(addin, "PowerTools Assembly", "Autodesk Fusion add-in")
  System_Ext(fusion, "Autodesk Fusion", "Host application and Python API (adsk.core / adsk.fusion)")
  System_Ext(hub, "Autodesk Hub", "Cloud document storage providing reference version data")
  System_Ext(fs, "Local File System", "Log file output destination")

  Rel(user, addin, "Runs Bottom-Up Update")
  Rel(addin, fusion, "Traverses assembly DAG; opens, updates, rebuilds, and saves each component document in order")
  Rel(fusion, hub, "Downloads latest reference versions during updateAllReferences(); saves updated documents")
  Rel(addin, fs, "Writes timestamped log file")
```

```mermaid
C4Component
  title Bottom-Up Update – Component View

  Person(user, "Design Engineer")
  Component(cmd, "bottomupupdate/entry.py", "PowerTools Command", "Registers toolbar button; presents three-tab dialog; orchestrates the full bottom-up update lifecycle")
  Component(traversal, "traverse_assembly()", "Internal Function", "Recursively builds a nested dictionary representing the full assembly dependency tree")
  Component(dag_sort, "sort_dag_bottom_up()", "Internal Function", "Topologically sorts the dependency tree so leaves are processed before parents")
  Component(api_design, "adsk.fusion.Design", "Fusion API", "Provides allComponents, rootComponent, and occurrences for traversal")
  Component(api_doc, "adsk.core.Document", "Fusion API", "Opened per component for updateAllReferences(), computeAll(), and save()")
  Component(intent, "Design Intent Logic", "Internal Logic", "Analyzes child occurrences, sketches, and bodies; executes appropriate Fusion text command")
  Component(logger, "Log Writer", "Internal Function", "Writes timestamped UTF-8 text log to the selected path")
  System_Ext(hub, "Autodesk Hub", "Stores versioned component documents")

  Rel(user, cmd, "Clicks Bottom-up Update button")
  Rel(cmd, traversal, "Builds dependency tree from rootComponent.occurrences")
  Rel(traversal, api_design, "Reads each component's child occurrences")
  Rel(cmd, dag_sort, "Determines bottom-up processing order")
  Rel(cmd, api_doc, "Opens each component in turn; calls updateAllReferences and computeAll; saves")
  Rel(api_doc, hub, "Pulls latest reference versions; pushes saved versions")
  Rel(cmd, intent, "Applies classification when Apply Design Doc Intent is enabled")
  Rel(cmd, logger, "Writes event and summary entries")
```

### Topological sort

The command must process components in an order where every component's dependencies are saved before the component that uses them. It achieves this through a two-phase algorithm.

**Phase 1 — Build the dependency tree (`traverse_assembly`)**

Starting from the root component, the function walks `component.occurrences` recursively. Each component is stored as a node in a nested dictionary keyed by component name:

```
{
  "Bracket": {
    "component": <adsk.fusion.Component>,
    "children": {
      "Bushing": { "component": ..., "children": {} },
      "Pin":     { "component": ..., "children": {} }
    }
  },
  "Frame": { ... }
}
```

The result is a directed acyclic graph (DAG) where each node points to its child nodes. Components that appear in multiple sub-assemblies are represented once under the first parent that encounters them; duplicate traversal of the same component name is skipped.

**Phase 2 — Post-order traversal (`sort_dag_bottom_up`)**

The sort walks the DAG using a depth-first, post-order traversal. For any given node it recurses into all children before appending the node itself to the output list. This guarantees that a component only appears in the list *after* all of its dependencies have already been appended.

```
traverse_dag("Bracket")
  → traverse_dag("Bushing")  → append "Bushing"
  → traverse_dag("Pin")      → append "Pin"
  → append "Bracket"
```

The final list is the bottom-up processing order. The command iterates it in sequence, opening, updating, and saving each document before moving to the next. The root assembly is excluded from the list and is saved separately at the end after all components have been processed.

**Why post-order matters**

If a parent component is saved before its children are up to date, Autodesk Fusion resolves the parent's references against the old version of each child. The post-order traversal eliminates this problem: by the time any parent document is opened and saved, every document it depends on has already been updated and saved to the Hub.

---

[Back to PowerTools Assembly](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
