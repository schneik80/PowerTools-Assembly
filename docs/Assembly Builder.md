# Assembly Builder

[Back to PowerTools Assembly](../README.md)

The Assembly Builder command opens a visual node editor that lets you design an assembly hierarchy before any components exist. You place Assembly, Part, and Hybrid nodes on a canvas, connect them to form a tree (optionally with shared children), optionally link project **global parameter** sets to specific components, then generate every external component in a single action. Each generated document is created with the correct design intent automatically, shared children are inserted by reference, and linked parameter sets are derived into the components that need them.

## What you can do

- Design an assembly hierarchy in a palette-based visual node editor powered by [Drawflow](https://github.com/jerosoler/Drawflow).
- Add **Assembly**, **Part**, and **Hybrid** nodes by clicking them in the sidebar.
- With a node selected, clicking a sidebar template adds the new node already connected as its child.
- Connect nodes by dragging from the output port (bottom) of a parent to the input port (top) of a child. Connector hit targets are enlarged so wiring is easy without enlarging the visible ports.
- Share a single child between multiple parents by connecting it to more than one parent.
- Add a **Global Parameters** node for any parameter set found in the active project's `_Global Parameters` folder, then connect it to the components that should derive it. Each parameter document can be added once; its button disables while it is on the canvas and re-enables if you delete the node.
- New nodes get incrementing default names per type (`Assembly 1`, `Part 1`, `Hybrid 1`, …); double-click a node's name to rename it before generating.
- **Arrange** lays the graph out as a clean org chart; zoom (Ctrl+scroll) and pan (drag empty canvas); use **Fit** to recenter.
- Generate every external component in one step with **Create Assembly**.
- Design intent is applied per node type automatically (Part / Assembly / Hybrid).
- Palette theme follows the Fusion UI theme — light, dark, or **match OS device theme** — and is correct on first paint.

## Prerequisites

- An Autodesk Fusion 3D Design must be active.
- The active document must be **new (unsaved)**, **or** a **saved document that is still empty** — no timeline features, bodies, sketches, or child components.
- The active design's design intent must be **Assembly** or **Hybrid** (not **Part**).
- The active design must have **no existing child components** at the root.

If any of these conditions is not met, Assembly Builder displays a message explaining what to change and does not open the palette.

> **Note:** When the design contains shared parts or linked global parameters, the document must be saved before generation (these need a cloud `DataFile`). A banner appears across the bottom of the palette and **Create Assembly** is disabled until you save (Ctrl+S); it re-enables automatically. A saved-but-empty starting document satisfies this immediately.

## How to use Assembly Builder

1. In Autodesk Fusion, create a new design with **File > New Design** (or open a saved, still-empty design).
2. Confirm the design intent is **Assembly** or **Hybrid**.
3. On the **Power Tools** panel in the Design workspace, select **Assembly Builder**.
4. Click an **Assembly**, **Part**, or **Hybrid** button in the palette sidebar to add a node to the canvas. Select an existing node first to add the new one already connected as its child.
5. Drag from the output port at the bottom of a parent node to the input port at the top of a child node to connect them.
6. Double-click a node's name to rename it. This name becomes the Fusion component name.
7. To share a child across multiple parents, connect the same child to more than one parent.
8. To apply a project parameter set, click its button under **Global Parameters** in the sidebar and connect the resulting node to each component that should derive it.
9. If the **save** banner is shown (shared parts or global parameters present), save the document (Ctrl+S). **Create Assembly** enables automatically.
10. When the hierarchy is complete, select **Create Assembly**.

Generation runs in three passes:

1. **Build** — the graph is walked top-down and `addNewExternalComponent` is called for each child, applying design intent per node type.
2. **Flush & shared inserts** — the document is saved once to flush the new external documents to cloud `DataFile`s, then each shared child is inserted into its additional parents via `addByInsert`.
3. **Derive parameters** — for every component linked to a parameter node, the component document is opened, the parameter set is derived in (favorite parameters, inserted first in the timeline), and the document is saved. Progress is shown in a dialog (one step per document) and each cloud upload is awaited so versions are current. Finally the root assembly pulls all references to latest (`updateAllReferences`) and is saved.

External component saves and the final root save use the comment **"Updated with Assembly Builder"**.

> **Note:** Because `addNewExternalComponent` requires an Autodesk Hub folder, the active project's root folder is used as the destination. You can move the generated documents afterward in the Data Panel.

> **Note:** All validation and result messages are shown as native Fusion message boxes — there are no browser alert dialogs.

## Access

The **Assembly Builder** command is located on the **Utilities** tab, in the **Power Tools** panel of the Autodesk Fusion Design workspace.

## Architecture

Assembly Builder bridges an HTML/JS palette (running in Fusion's QT WebEngine) and the Fusion Python API. The palette hosts the Drawflow node editor; the Python backend validates launch conditions, receives the exported graph, and creates documents.

```mermaid
C4Context
  title Assembly Builder – System Context

  Person(user, "Design Engineer", "Autodesk Fusion user designing a new assembly hierarchy")
  System(addin, "PowerTools Assembly", "Autodesk Fusion add-in")
  System_Ext(fusion, "Autodesk Fusion", "Host application and Python API (adsk.core / adsk.fusion)")
  System_Ext(hub, "Autodesk Hub", "Cloud folder storing generated external components")

  Rel(user, addin, "Runs Assembly Builder, designs hierarchy, clicks Create Assembly")
  Rel(addin, fusion, "Creates external components; sets design intent; inserts shared references")
  Rel(fusion, hub, "Stores generated documents as versioned cloud files")
```

```mermaid
C4Container
  title Assembly Builder – Container View

  Person(user, "Design Engineer")

  Container_Boundary(cmd, "Assembly Builder command") {
    Container(python, "Python Backend", "commands/assemblybuilder/entry.py", "Command lifecycle, launch guards, graph processing, component creation")
    Container(palette, "HTML Palette", "resources/html/index.html + drawflow", "Visual node editor, graph export, theme support")
    ContainerDb(graph, "Drawflow Graph", "JSON in memory", "Node positions, connections, metadata")
  }

  System_Ext(fusion, "Fusion API", "adsk.core, adsk.fusion")

  Rel(user, palette, "Adds nodes, connects, renames")
  Rel(palette, python, "fusionSendData('createAssembly', graph)")
  Rel(python, palette, "sendInfoToHTML('setTheme', 'setDocumentName')")
  Rel(python, fusion, "addNewExternalComponent, addByInsert, designIntent")
```

```mermaid
C4Component
  title Assembly Builder – Python Backend

  Container_Boundary(python, "Python Backend") {
    Component(entry, "entry.py", "Command entry point", "start/stop lifecycle, command execution, palette management")
    Component(guards, "Launch Guards", "Validation", "Checks: active Design, new-or-empty, intent != Part, no root children")
    Component(incoming, "palette_incoming", "Message handler", "Routes 'createAssembly'; shows native message boxes")
    Component(graph, "Graph Processor", "Assembly builder", "Parses Drawflow JSON, creates hierarchy top-down")
    Component(shared, "Shared Node Handler", "Reference manager", "Detects multi-parent nodes, defers insertions, saves for DataFile")
    Component(params, "Parameter Deriver", "Pass 3", "Opens linked docs, derives favorite params, waits uploads, get-latest")
  }

  System_Ext(fusion, "Fusion API")

  Rel(entry, guards, "Validates before showing palette")
  Rel(incoming, graph, "Passes parsed graph data")
  Rel(graph, shared, "Delegates shared components")
  Rel(graph, params, "Delegates parameter links")
  Rel(graph, fusion, "addNewExternalComponent, designIntent")
  Rel(shared, fusion, "save, addByInsert")
  Rel(params, fusion, "open, deriveFeatures, save, updateAllReferences")
```

```mermaid
C4Component
  title Assembly Builder – HTML Palette

  Container_Boundary(palette, "HTML Palette") {
    Component(drawflow, "Drawflow Editor", "drawflow.min.js", "Node canvas with zoom, pan, connections")
    Component(sidebar, "Sidebar", "Click-to-add", "Assembly/Part/Hybrid + Global Parameters buttons")
    Component(toolbar, "Toolbar", "Action buttons", "Fit, Arrange, Clear All, Create Assembly, zoom")
    Component(theme, "Theme Engine", "CSS custom properties", "Dark/light via body class, set before first paint")
    Component(init, "init.js", "Generated sidecar", "window.__ptInit: theme, doc name, save state, param docs")
    Component(bridge, "Fusion Bridge", "fusionJavaScriptHandler", "Reopen refresh: theme/doc/saveState/paramDocs")
    Component(export, "Graph Export", "createAssembly()", "Exports Drawflow JSON, sends via fusionSendData")
  }

  Rel(sidebar, drawflow, "addNode() / addParamDocNode()")
  Rel(toolbar, drawflow, "zoom_in/out, clear, fitToView, arrangeLayout")
  Rel(toolbar, export, "Create Assembly click")
  Rel(export, drawflow, "editor.export()")
  Rel(init, theme, "applies theme synchronously")
  Rel(bridge, theme, "setTheme (reopen)")
  Rel(bridge, drawflow, "setDocumentName / setParamDocs")
```

### Assembly creation sequence

```mermaid
sequenceDiagram
    participant User
    participant Palette as HTML Palette
    participant Python as Python Backend
    participant Fusion as Fusion API

    User->>Palette: Click "Create Assembly"
    Palette->>Palette: editor.export() -> JSON graph
    Palette->>Python: fusionSendData('createAssembly', graph)

    Python->>Python: Parse JSON, find root, detect shared + param links

    rect rgb(238,244,250)
    note right of Python: Pass 1 — build
    loop For each structural child (top-down)
        Python->>Fusion: addNewExternalComponent(name, folder, transform)
        Python->>Fusion: design.designIntent = type
    end
    end

    rect rgb(238,244,250)
    note right of Python: Pass 2 — flush + shared inserts
    Python->>Fusion: doc.save() [flush external docs]
    loop For each deferred shared insert
        Python->>Fusion: addByInsert(dataFile, transform, true)
    end
    end

    opt Parameter links exist
    rect rgb(238,244,250)
    note right of Python: Pass 3 — derive params (progress dialog)
    loop For each linked component
        Python->>Fusion: documents.open(dataFile)
        Python->>Fusion: deriveFeatures (favorite params)
        Python->>Fusion: doc.save("Updated with Assembly Builder")
        Python->>Fusion: wait_for_upload(...)
    end
    Python->>Fusion: root.updateAllReferences() + save
    end
    end

    Python->>Palette: Hide palette
    Python->>Fusion: ui.messageBox (native result/warnings)
    Fusion-->>User: Result message
```

### Drawflow graph data model

```mermaid
erDiagram
    GRAPH ||--o{ NODE : contains
    NODE ||--o{ OUTPUT : has
    NODE ||--o{ INPUT : has
    OUTPUT ||--o{ CONNECTION : connects_to
    INPUT ||--o{ CONNECTION : connects_from

    NODE {
        int id
        string name "node type: root, assembly, part, hybrid, paramdoc"
        string class "is-root / is-paramdoc"
        float pos_x
        float pos_y
        json data "name (display); paramId + paramName for paramdoc nodes"
    }

    CONNECTION {
        string node "target node id"
        string output "port name"
    }
```

## Design decisions

### Why Drawflow over Flowy?
Flowy only supports tree structures with connections made at drop time. Drawflow supports arbitrary connections between existing nodes, shared components (multi-parent), built-in zoom/pan, and a simpler API.

### Why click-to-add instead of drag-and-drop?
Fusion's QT WebEngine palette intercepts native HTML5 drag events at the widget level before they reach the Chromium rendering layer. Click-to-add uses standard mouse events, which work reliably across Windows and macOS.

### Why top-down creation with `addNewExternalComponent`?
Top-down creation builds the structural tree first. A single flush save then establishes the cloud `DataFile` references that `addByInsert` (shared parts) and document-open (parameter derive) both require — without ever surfacing Fusion's save-as dialog mid-run.

### Why a separate parameter-derive pass?
Deriving favorite parameters requires opening each target component as its own document (the same mechanism used by **Link Global Parameters**). Doing this after the tree is built and flushed means every target already has a `DataFile`. Each per-document save is awaited (cloud uploads are asynchronous) before the root runs `updateAllReferences()`, so the assembly references the freshly-derived versions rather than stale ones.

### Why direct global-parameter links instead of a global toggle?
A `paramdoc` node's output connects to the input of each component that should derive it, so the graph itself records exactly which components get which parameter set — parts included (parts have no output port, so the link is made into the part's input). Each parameter document can be added only once; its sidebar button reflects whether the node is on the canvas.

### Why a generated `init.js` instead of a message handshake?
Fusion's palette loads asynchronously, and `palettes.add()` rejects a query string on the URL. Writing `resources/html/init.js` (theme, document name, save state, parameter docs) **before** creating the palette lets the page read `window.__ptInit` synchronously and apply the theme before the first paint — deterministic, with no round-trip and no flicker. A reopened palette (page already loaded) is refreshed via `sendInfoToHTML` instead.

### Why top-to-bottom node layout?
Assembly hierarchies read naturally as trees flowing downward. Input ports at 12 o'clock (parent connection) and output ports at 6 o'clock (child connections) match this mental model.

---

[Back to PowerTools Assembly](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
