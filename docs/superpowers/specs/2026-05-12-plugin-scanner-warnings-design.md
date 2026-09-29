# Design: Refactor PluginScanner for Explicit Warnings

Refactor `PluginScanner` to return `tuple[data, warnings]` instead of just `data`, consistent with the codebase-wide refactoring of scanners.

## Architecture
Modify the `scan()` method in `PluginScanner` to return a tuple. The first element is the scanned plugin data dictionary, and the second element is a list of warning strings.

## Components

### 1. `PluginScanner.scan`
- Change signature to return `tuple[Dict[str, Dict[str, Any]], List[str]]`.
- Initialize `warnings = []`.
- Wrap `json.load(f)` in a `try...except Exception` block.
- On exception:
    - Append a descriptive warning to `warnings`.
    - If `CA_DEBUG` environment variable is set, print the traceback.
    - `continue` to the next plugin directory.
- Return `(result, warnings)`.

### 2. `get_plugins_to_mount`
- Update to unpack the result from `scanner.scan()`.
- Update the recursive call for `local_scanner.scan()`.

## Data Flow
`PluginScanner.scan()` -> `(scanned_data, warnings)` -> `get_plugins_to_mount()` -> caller.

## Error Handling
- Invalid JSON in `metadata.json` will be caught and reported as a warning instead of silently ignored (or crashing).
- `CA_DEBUG=1` will enable traceback printing for these errors.

## Testing
- Update existing tests in `tests/test_plugin.py` to handle the new return type.
- Add a new test case `test_plugin_scanner_invalid_json` to verify warning generation and `CA_DEBUG` behavior.
