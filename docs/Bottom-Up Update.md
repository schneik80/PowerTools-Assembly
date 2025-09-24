# Bottom-Up Update

The Bottom-Up Update command processes assembly components in dependency order, updating and saving each component from the bottom of the hierarchy upward. This ensures that all references are properly updated before dependent components are processed.

## Overview

This command is designed to update complex assemblies by:
- Analyzing the assembly structure to determine component dependencies
- Processing components in bottom-up order (dependencies first)
- Opening each component document individually
- Updating references and applying design intent
- Optionally hiding various UI elements for cleaner saves
- Rebuilding and saving each component
- Providing detailed logging of the entire process

## Prerequisites

Before running the Bottom-Up Update command:

1. **Active Design Document**: A Fusion 360 design document must be active
2. **Saved Document**: The active document must be saved
3. **References Present**: The document must contain references to other components
4. **File Access**: Ensure you have write access to all component files that will be processed

## Command Dialog

The Bottom-Up Update dialog is organized into three tabs:

### Main Tab

The Main tab contains the core processing options:

#### Rebuild all
- **Default**: Enabled
- **Description**: Forces a complete rebuild of all components to ensure they are up to date
- **Recommendation**: Keep enabled unless you specifically need to preserve the current state

#### Skip standard components
- **Default**: Enabled  
- **Description**: Skips processing of standard library components during the update
- **Recommendation**: Keep enabled to avoid unnecessary processing of library components

#### Skip already saved Documents
- **Default**: Disabled
- **Description**: Skips components that have already been saved in this Fusion client build
- **Use Case**: Useful when re-running the command after a partial completion or system interruption

#### Apply Design Doc Intent
- **Default**: Disabled
- **Description**: Automatically applies the appropriate design intent to each component based on its content:
  - **Part Intent**: Applied to components with no child components (leaf nodes)
  - **Assembly Intent**: Applied to components with child components but no sketches or bodies
  - **Hybrid Assembly Intent**: Applied to components with both child components AND sketches or bodies
- **Benefits**: Ensures proper component classification and optimizes Fusion 360 performance

### Visibility Tab

The Visibility tab provides options to hide various UI elements during processing:

#### Hide origins
- **Default**: Disabled
- **Description**: Hides the coordinate system origins in each component before saving
- **Use Case**: Creates cleaner component files without visible coordinate systems

#### Hide joints
- **Default**: Disabled
- **Description**: Hides all joints in each component before saving. Sets the Joints folder visibility off so new joints DO NOT appear and clutter the canvas.
- **Use Case**: Useful for presentations or when joints clutter the component view

#### Hide sketches
- **Default**: Disabled
- **Description**: Hides all sketches in each component before saving. Sets the Sketches folder visibility On so new sketches appear as expected.
- **Use Case**: Creates cleaner final components by hiding construction sketches

#### Hide joint origins
- **Default**: Disabled
- **Description**: Hides all joint origin markers in each component before saving. Sets the Joint Origins folder visibility On so new Joint Origins appear as expected.
- **Use Case**: Removes joint reference points for cleaner component appearance

#### Hide canvases
- **Default**: Disabled
- **Description**: Hides all canvases in each component before saving. Sets the Canvases folder visibility On so new canvases appear as expected.
- **Use Case**: Hides canvas elements that may not be needed in final components

### Logging Tab

The Logging tab controls the detailed logging functionality:

#### Log Progress
- **Default**: Enabled
- **Description**: Enables detailed progress logging to a text file during the update process
- **Benefits**: 
  - Track which components were processed
  - Debug issues with specific components
  - Maintain an audit trail of changes
  - Monitor processing time and performance

#### Log File Location
- **Default**: Auto-generated filename in the user's Documents folder
- **Description**: Click "Browse…" to select a custom location for the log file
- **Auto-naming**: If not specified, uses format: `[DocumentName].txt` in ~/Documents
- **File Format**: Plain text (.txt) files with UTF-8 encoding

## Processing Flow

When you execute the command, the following process occurs:

### 1. Assembly Analysis
- Traverses the entire assembly structure recursively
- Identifies all component dependencies using a directed acyclic graph (DAG)
- Creates a dependency tree of the assembly structure
- Generates processing order based on component relationships

### 2. Dependency Ordering
- Sorts components in bottom-up order using topological sorting
- Ensures dependencies are processed before dependent components
- Reports the processing order in the log
- Skips the root component (processed separately at the end)

### 3. Component Processing
For each component in dependency order:
- **Document Management**: Opens the component document for editing
- **Reference Updates**: Updates all references in the component using `updateAllReferences()`
- **Workspace Activation**: Ensures proper Fusion Solid Environment workspace is active
- **Visibility Controls**: Applies selected visibility options (hide origins, sketches, joints, etc.)
- **Design Intent Application**: Applies appropriate design intent based on component content:
  - Analyzes child components, sketches, and bodies
  - Executes appropriate Fusion text commands for intent classification
- **Rebuilding**: Forces complete rebuild if rebuild option is enabled using `computeAll()`
- **Change Detection**: Adds/removes temporary attributes to trigger change detection
- **Document Saving**: Saves with timestamp and version information
- **Cleanup**: Closes the component document

### 4. Final Assembly Updates
- Executes "Get All Latest" command to ensure current versions
- Executes "Update All From Parent" command to refresh all references
- Saves the main assembly document
- Provides completion statistics

### 5. Completion
- Reports final statistics (components processed, time taken)
- Clears all temporary data and global variables for subsequent runs
- Displays completion message with log file location

## Logging Output

When logging is enabled, the log file contains:

### Header Information
- Active document parent project name and document ID
- Command execution timestamp and configuration options
- Bottom-up processing order (complete component list)

### Processing Details
For each component:
- Document open/close events with timestamps
- Reference update confirmations
- Visibility changes applied (with counts of affected elements)
- Design intent application results with detailed reasoning
- Rebuild completion confirmations
- Save events with timestamps
- Any errors or warnings encountered

### Summary Statistics
- Total components processed successfully
- Total processing time in seconds
- Final completion status
- Global variable cleanup confirmation

## Design Intent Logic

The Apply Design Doc Intent feature uses intelligent analysis to determine the appropriate intent:

### Part Intent
- **Criteria**: Component has no child components (occurrences.count == 0)
- **Command**: `Fusion.setDocumentExperience Part`
- **Use Case**: Leaf components that contain only geometry

### Assembly Intent  
- **Criteria**: Component has child components but no sketches or bodies
- **Command**: `Fusion.setDocumentExperience xrefAssembly`
- **Use Case**: Pure assemblies that only contain other components

### Hybrid Assembly Intent
- **Criteria**: Component has child components AND contains sketches or bodies
- **Command**: `Fusion.setDocumentExperience xrefAssembly hybridAssembly`
- **Use Case**: Assemblies that also contain native geometry or construction elements

## Best Practices

### Before Running
1. **Save your work**: Ensure the active document is saved
2. **Close other documents**: Close unnecessary documents to avoid confusion
3. **Check file permissions**: Ensure all component files are writable
4. **Review options**: Configure the dialog options based on your needs
5. **Plan for time**: Large assemblies may take significant time to process

### During Execution
1. **Monitor progress**: Watch the Text Commands window for progress updates
2. **Don't interrupt**: Allow the command to complete fully to avoid corrupted states
3. **Check for errors**: Review any error messages that appear
4. **System resources**: Ensure adequate system memory and disk space

### After Completion
1. **Review the log**: Check the log file for any issues or warnings
2. **Verify results**: Spot-check a few components to ensure proper processing
3. **Test assemblies**: Verify that assembly relationships are maintained
4. **Check intent**: Confirm design intent was applied correctly if enabled

## Common Use Cases

### Assembly Maintenance
- When component files have been modified externally
- After importing updated components from other sources
- When references need to be refreshed across an assembly
- Regular cleanup and optimization of assembly files

### Batch Processing
- Applying consistent visibility settings across all components
- Hiding construction elements for presentation purposes
- Applying design intent classification to all components
- Standardizing component appearance and structure

### Project Preparation
- Preparing assemblies for sharing or collaboration
- Cleaning up assemblies before archiving projects
- Optimizing performance through proper design intent classification
- Creating presentation-ready assemblies with hidden construction elements

## Troubleshooting

### Common Issues

**"No document references found" error**
- The active document doesn't contain any external references
- Ensure you're running the command on an assembly with linked components

**Components not processing**
- Check file permissions on component files
- Ensure referenced files are accessible and not locked by other users
- Review the log file for specific error messages
- Verify network connectivity for cloud-based projects

**Incomplete processing**
- Use "Skip already saved Documents" option to resume from where it left off
- Check available disk space for temporary files and saves
- Ensure Fusion 360 has sufficient memory allocation
- Consider processing smaller sub-assemblies separately

**Design Intent application failures**
- Ensure components are not locked or read-only
- Check that the workspace is properly activated
- Review log file for specific intent application errors
- Verify component has the expected content (sketches, bodies, children)

### Performance Tips

- Close unnecessary applications to free up system resources
- Process smaller sub-assemblies separately for very large assemblies
- Use the skip options strategically to avoid unnecessary processing
- Enable logging only when needed for debugging (adds processing overhead)
- Ensure adequate RAM and fast storage for large assembly processing

## Integration

The Bottom-Up Update command integrates with other PowerTools commands:
- Use after bulk import operations to ensure all references are current
- Combine with other assembly management tools in workflows
- Part of larger assembly maintenance and optimization workflows
- Complements other PowerTools for comprehensive assembly management

## Technical Notes

### Version Tracking
- Uses Fusion 360 version information in save comments
- Tracks processing with current Fusion build version
- Maintains compatibility across Fusion updates

### Memory Management
- Clears global variables after each execution
- Tracks processed documents to avoid duplicates
- Implements proper cleanup for large assembly processing

### Error Handling
- Comprehensive exception handling for robust operation
- Detailed error logging for troubleshooting
- Graceful recovery from individual component failures

For additional help or to report issues, please refer to the main PowerTools documentation or submit an issue on the project repository.