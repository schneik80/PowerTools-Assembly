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

#### Skip already saved components
- **Default**: Disabled
- **Description**: Skips components that have already been saved in this session
- **Use Case**: Useful when re-running the command after a partial completion

#### Apply Design Doc Intent
- **Default**: Disabled
- **Description**: Applies design intent settings before saving each component
- **Note**: This ensures proper component classification (Part, Assembly, or Hybrid)

### Visualization Tab

The Visualization tab provides options to hide various UI elements during processing:

#### Hide origins
- **Default**: Disabled
- **Description**: Hides the coordinate system origins in each component before saving
- **Use Case**: Creates cleaner component files without visible coordinate systems

#### Hide joints
- **Default**: Disabled
- **Description**: Hides all joints in each component before saving. Ensures the Joints folder is off so new joints DO NOT appear and clutter the canvas.
- **Use Case**: Useful for presentations or when joints clutter the component view

#### Hide sketches
- **Default**: Disabled
- **Description**: Hides all sketches in each component before saving. Ensures the Sketch folder is on so new sketches appear as expected.
- **Use Case**: Creates cleaner final components by hiding construction sketches

#### Hide joint origins
- **Default**: Disabled
- **Description**: Hides all joint origin markers in each component before saving. Ensures the Joint Origins folder is on so new Joint Origins appear as expected.
- **Use Case**: Removes joint reference points for cleaner component appearance

#### Hide canvases
- **Default**: Disabled
- **Description**: Hides all canvases in each component before saving. Ensures the Canvas folder is on so new canvases appear as expected.
- **Use Case**: Hides canvas elements that may not be needed in final components

### Logging Tab

The Logging tab controls the detailed logging functionality:

#### Log Progress
- **Default**: Disabled
- **Description**: Enables detailed progress logging to a text file during the update process
- **Benefits**: 
  - Track which components were processed
  - Debug issues with specific components
  - Maintain an audit trail of changes
  - Monitor processing time and performance

#### Log File Location
- **Default**: Auto-generated filename in the project folder
- **Description**: Click "Browse…" to select a custom location for the log file
- **Auto-naming**: If not specified, uses format: `BottomUpUpdate_[ProjectName]_[Timestamp].log`

## Processing Flow

When you execute the command, the following process occurs:

### 1. Assembly Analysis
- Traverses the entire assembly structure
- Identifies all component dependencies
- Creates a dependency graph
- Generates an ASCII tree diagram of the assembly structure

### 2. Dependency Ordering
- Sorts components in bottom-up order using topological sorting
- Ensures dependencies are processed before dependent components
- Reports the processing order in the log

### 3. Component Processing
For each component in dependency order:
- Opens the component document
- Logs the open event
- Updates all references in the component
- Applies selected visualization options (hide origins, sketches, etc.)
- Applies design intent if enabled
- Rebuilds the component if rebuild option is enabled
- Saves the component
- Closes the component document

### 4. Completion
- Reports final statistics (components processed, time taken)
- Clears all temporary data for subsequent runs
- Displays completion message

## Logging Output

When logging is enabled, the log file contains:

### Header Information
- Command execution timestamp
- Assembly structure (ASCII tree diagram)
- Processing order (bottom-up component list)
- Configuration options used

### Processing Details
For each component:
- Document open events
- Reference update results
- Visualization changes applied
- Design intent application results
- Rebuild and save confirmation
- Any errors or warnings encountered

### Summary Statistics
- Total components processed
- Total processing time
- Success/failure counts
- Final completion status

## Best Practices

### Before Running
1. **Save your work**: Ensure the active document is saved
2. **Close other documents**: Close unnecessary documents to avoid confusion
3. **Check file permissions**: Ensure all component files are writable
4. **Review options**: Configure the dialog options based on your needs

### During Execution
1. **Monitor progress**: Watch the Text Commands window for progress updates
2. **Don't interrupt**: Allow the command to complete fully
3. **Check for errors**: Review any error messages that appear

### After Completion
1. **Review the log**: Check the log file for any issues or warnings
2. **Verify results**: Spot-check a few components to ensure proper processing
3. **Test assemblies**: Verify that assembly relationships are maintained

## Common Use Cases

### Assembly Updates
- When component files have been modified externally
- After importing updated components from other sources
- When references need to be refreshed across an assembly

### Batch Processing
- Applying consistent settings across all components
- Hiding construction elements for presentation purposes
- Applying design intent classification to all components

### Maintenance
- Regular cleanup of assembly files
- Preparation for sharing or archiving projects
- Standardizing component appearance and structure

## Troubleshooting

### Common Issues

**"No references to update" error**
- The active document doesn't contain any external references
- Ensure you're running the command on an assembly with linked components

**Components not processing**
- Check file permissions on component files
- Ensure referenced files are accessible and not locked
- Review the log file for specific error messages

**Incomplete processing**
- Use "Skip already saved components" option to resume from where it left off
- Check available disk space
- Ensure Fusion 360 has sufficient memory

### Performance Tips

- Close unnecessary applications to free up system resources
- Process smaller sub-assemblies separately for very large assemblies
- Use the skip options to avoid unnecessary processing
- Enable logging only when needed for debugging

## Integration

The Bottom-Up Update command integrates with other PowerTools commands:
- Use after bulk import operations
- Combine with other assembly management tools
- Part of larger assembly maintenance workflows

For additional help or to report issues, please refer to the main PowerTools documentation or submit an issue on the project repository.