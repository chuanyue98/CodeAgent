# Design: Explicit Error Handling in ConfigService

Refactor `ConfigService` to explicitly handle errors during configuration loading and return warnings alongside the data.

## 1. Architecture & Components

### `ConfigService.get_config`
- **Current Signature**: `get_config(self) -> dict`
- **New Signature**: `get_config(self) -> tuple[dict, list[str]]`
- **Behavior**:
    - Returns `({}, [])` if the configuration file does not exist.
    - Returns `(data, [])` if the file is successfully parsed.
    - Returns `({}, ["Failed to parse config.json: <error_message>"])` if a `json.JSONDecodeError` or other exception occurs during reading/parsing.
    - If the `CA_DEBUG` environment variable is set, it prints the exception traceback to stderr.

### Internal Callers
- `add_project` and `delete_project` call `get_config`. They will be updated to unpack the tuple: `config, _ = self.get_config()`.

## 2. Testing Strategy

### Unit Tests (`tests/test_config_service.py`)
- **Compatibility**: Update existing tests to assert against the `(data, warnings)` tuple.
- **Parse Error**: Add a test case where `config.json` contains invalid JSON and verify that `get_config` returns an empty dict and a non-empty list of warnings.
- **Missing File**: Verify that `get_config` returns `({}, [])` when the file is missing.

## 3. Implementation Details

- Use `os.getenv("CA_DEBUG")` to check for debug mode.
- Use `traceback.print_exc()` for debug output.
- Ensure all callers of `get_config` in the codebase (if any beyond `ConfigService` itself) are identified and updated.

## 4. Verification

- `pytest tests/test_config_service.py`
- Manual check with a malformed `config.json`.
