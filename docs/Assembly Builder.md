# Assembly Builder

[Back to PowerTools Assembly](../README.md)

The Assembly Builder command opens a visual node editor that lets you design an assembly hierarchy before any components exist. You place Assembly, Part, and Hybrid nodes on a canvas, connect them to form a tree (optionally with shared children), then generate every external component in a single action. Each generated document is created with the correct design intent automatically.

## What you can do

- Design an assembly hierarchy in a palette-based visual node editor powered by [Drawflow](https://github.com/jerosoler/Drawflow).
- Add **Assembly**, **Part**, and **Hybrid** nodes by clicking them in the sidebar.
- Connect nodes by dragging from the output port (bottom) of a parent to the input port (top) of a child.
- Share a single child between multiple parents by connecting it to more than one output.
- Double-click a node's name to rename it before generating.
- Zoom (Ctrl+scroll) and pan (drag empty canvas); use **Fit** to recenter.
- Generate every external component in one step with **Create Assembly**.
- Design intent is applied per node type automatically (Part / Assembly / Hybrid).
- Palette theme follows the Fusion UI theme (light or dark).

## Prerequisites

- An Autodesk Fusion 3D Design must be active.
- The active document must be **new and unsaved** — create it with **File > New Design** immediately before running the command.
- The active design's design intent must be **Assembly** or **Hybrid** (not **Part**).
- The active design must have **no existing child components** at the root.

If any of these conditions is not met, Assembly Builder displays a message explaining what to change and does not open the palette.

## How to use Assembly Builder

1. In Autodesk Fusion, create a new design with **File > New Design**.
2. Confirm the design intent is **Assembly** or **Hybrid**.
3. On the **Power Tools** panel in the Design workspace, select **Assembly Builder**.
4. Click an **Assembly**, **Part**, or **Hybrid** button in the palette sidebar to add a node to the canvas.
5. Drag from the output port at the bottom of a parent node to the input port at the top of a child node to connect them.
6. Double-click a node's name to rename it. This name becomes the Fusion component name.
7. To share a child across multiple parents, connect the same child to more than one parent output.
8. When the hierarchy is complete, select **Create Assembly**.

The command walks the graph top-down and calls `addNewExternalComponent` for each child. If any nodes are shared (connected to multiple parents), the document is saved once automatically to establish cloud `DataFile` references, then `addByInsert` is used to insert the shared component into the additional parents.

> **Note:** Assembly Builder creates external components without saving the overall assembly. After you inspect the generated hierarchy, save the active document manually when you are ready.

> **Note:** Because `addNewExternalComponent` requires an Autodesk Hub folder, the active project's root folder is used as the destination. You can move the generated documents afterward in the Data Panel.

## Access

The **Assembly Builder** command is located on the **Power Tools** panel in the Autodesk Fusion Design workspace.

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
    Component(guards, "Launch Guards", "Validation", "Checks: active Design, unsaved, intent != Part, no root children")
    Component(incoming, "palette_incoming", "Message handler", "Routes 'createAssembly' action to graph processor")
    Component(graph, "Graph Processor", "Assembly builder", "Parses Drawflow JSON, creates hierarchy top-down")
    Component(shared, "Shared Node Handler", "Reference manager", "Detects multi-parent nodes, defers insertions, saves for DataFile")
  }

  System_Ext(fusion, "Fusion API")

  Rel(entry, guards, "Validates before showing palette")
  Rel(incoming, graph, "Passes parsed graph data")
  Rel(graph, shared, "Delegates shared components")
  Rel(graph, fusion, "addNewExternalComponent, designIntent")
  Rel(shared, fusion, "save, addByInsert")
```

```mermaid
C4Component
  title Assembly Builder – HTML Palette

  Container_Boundary(palette, "HTML Palette") {
    Component(drawflow, "Drawflow Editor", "drawflow.min.js", "Node canvas with zoom, pan, connections")
    Component(sidebar, "Sidebar", "Click-to-add", "Assembly, Part, Hybrid node templates")
    Component(toolbar, "Toolbar", "Action buttons", "Fit, Clear All, Create Assembly, zoom controls")
    Component(theme, "Theme Engine", "CSS custom properties", "Dark/light mode via body class")
    Component(bridge, "Fusion Bridge", "fusionJavaScriptHandler", "Receives theme, doc name from Python")
    Component(export, "Graph Export", "createAssembly()", "Exports Drawflow JSON, sends via fusionSendData")
  }

  Rel(sidebar, drawflow, "addNode()")
  Rel(toolbar, drawflow, "zoom_in/out, clear, fitToView")
  Rel(toolbar, export, "Create Assembly click")
  Rel(export, drawflow, "editor.export()")
  Rel(bridge, theme, "setTheme action")
  Rel(bridge, drawflow, "setDocumentName action")
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

    Python->>Python: Parse Drawflow JSON
    Python->>Python: Find root node
    Python->>Python: Detect shared nodes

    loop For each child (top-down)
        Python->>Fusion: addNewExternalComponent(name, folder, transform)
        Fusion-->>Python: Occurrence
        Python->>Fusion: design.designIntent = type
    end

    opt Shared components exist
        Python->>Fusion: doc.save() [intermediate]
        loop For each deferred insert
            Python->>Fusion: addByInsert(dataFile, transform, true)
        end
    end

    Python->>Palette: Hide palette
    Python-->>Palette: "Created N components"
    Palette-->>User: Success message
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
        string name "node type: root, assembly, part, hybrid"
        string class "is-root for root node"
        float pos_x
        float pos_y
        json data "name field for display name"
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
Top-down creation builds components in-memory without requiring a save, so the user retains full control over when to save. Only shared components (multi-parent nodes) trigger an intermediate save — needed to establish the cloud `DataFile` references that `addByInsert` requires.

### Why top-to-bottom node layout?
Assembly hierarchies read naturally as trees flowing downward. Input ports at 12 o'clock (parent connection) and output ports at 6 o'clock (child connections) match this mental model.

---

[Back to PowerTools Assembly](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
