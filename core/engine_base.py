#!/usr/bin/env python3
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, BinaryIO, Callable, Dict, List, Optional, cast

from core.config_manager import ConfigManager
from core.hook_scanner import HookScanner, get_hooks_to_inject
from core.link_manager import LinkManager
from core.lock_manager import LockManager
from core.plugin_scanner import PluginScanner, get_plugins_to_mount
from core.prompt_kit import prompt_general, prompt_review
from core.prompt_scanner import PromptScanner, get_prompts_to_inject
from core.settings_manager import SettingsManager
from core.skill_scanner import SkillScanner, get_skills_to_mount


def register_signal_handler() -> None:
    """Install a SIGTERM handler that triggers a clean exit.

    The handler raises ``SystemExit`` via ``sys.exit()``, which ensures
    ``finally`` blocks execute — so per-engine cleanup (restore settings,
    remove symlinks, …) runs before the process terminates.  SIGKILL
    cannot be caught, but this covers the common case of OS/service-manager
    shutdown and manual ``kill <pid>``.
    """

    def _sigterm_handler(signum: int, frame: object) -> None:
        sys.exit(128 + signum)

    signal.signal(signal.SIGTERM, _sigterm_handler)


class EnvironmentManager:
    """Manages environment variables for the CodeAgent execution environment.

    Attributes:
        root_dir (Path): The root directory of the CodeAgent project.
    """

    def __init__(self, root_dir: Path):
        """Initializes EnvironmentManager with the project root directory.

        Args:
            root_dir (Path): The root directory of the CodeAgent project.
        """
        self.root_dir = root_dir

    def get_env(self) -> dict:
        """Returns a copy of the current environment variables with CodeAgent specific variables added.

        Returns:
            dict: A dictionary containing environment variables, including 'CODEAGENT_PATH'.
        """
        env = os.environ.copy()
        env["CODEAGENT_PATH"] = str(self.root_dir.absolute()).replace("\\", "/")
        return env


class BaseEngine:
    """Abstract base class for LLM engines.

    Subclasses declare EVENT_MAP to translate canonical hook event names
    (e.g. ``before_tool``) to the vendor-specific names their settings file expects.

    Provides core functionality for configuration management, environment setup,
    resource discovery (skills, prompts, hooks, plugins), and prompt assembly.

    Attributes:
        name (str): The unique name of the engine (e.g., 'gemini', 'claude').
        default_model (str): The default LLM model name to use.
        root_dir (Path): The root directory of the CodeAgent project.
        full_config (dict): The complete configuration loaded from config.json.
        env_manager (EnvironmentManager): Manager for environment variables.
        temp_prompt_name (str): Filename for the temporary prompt file.
        skill_scanner (SkillScanner): Scanner for discovering skills.
        prompt_scanner (PromptScanner): Scanner for discovering prompts.
        hook_scanner (HookScanner): Scanner for discovering hooks.
        plugin_scanner (PluginScanner): Scanner for discovering plugins.
    """

    EVENT_MAP: dict = {}

    def __init__(self, name: str, default_model: str):
        """Initializes the BaseEngine with its core components.

        Args:
            name (str): The name of the engine.
            default_model (str): The default model to be used by this engine.
        """
        self.name = name
        self.default_model = default_model
        self.root_dir = Path(__file__).resolve().parent.parent
        self.config_manager = ConfigManager(self.root_dir)
        self.full_config = self.config_manager.full_config
        self.env_manager = EnvironmentManager(self.root_dir)
        self.temp_prompt_name = ".ca_prompt.tmp"
        self._temp_prompt_paths: set[Path] = set()
        self.link_manager = LinkManager()
        self.lock_manager = LockManager()
        self.settings_manager = SettingsManager(self.EVENT_MAP)
        resource_root = self.config_manager.resolve_resource_root()
        self.skill_scanner = SkillScanner(resource_root / "skills")
        self.prompt_scanner = PromptScanner(resource_root / "prompt")
        self.hook_scanner = HookScanner(self.config_manager.get_hook_search_roots(resource_root))
        self.plugin_scanner = PluginScanner(resource_root / "plugins")

    def _resolve_resource_root(self) -> Path:
        return self.config_manager.resolve_resource_root()

    def _load_full_config(self) -> dict:
        return self.config_manager.full_config

    def _resolve_config_groups(self, section_name: str) -> List[str]:
        cfg = self.full_config.get(section_name, {})
        groups = cfg.get("groups", {})
        mappings = cfg.get("project_mapping", [])
        default_group = cfg.get("default_group", "common")

        cwd_str = str(Path.cwd().as_posix())
        selected_group_name = default_group

        for mapping in mappings:
            pattern = mapping.get("pattern")
            if pattern:
                if re.search(pattern, cwd_str, re.IGNORECASE):
                    selected_group_name = mapping.get("group")
                    break

        if section_name == "prompts":
            print(f"🎯 Prompts matched group: [{selected_group_name}]")

        def resolve(name, visited=None):
            if visited is None:
                visited = set()
            if name in visited:
                return []

            visited.add(name)

            result = []
            if name in groups:
                for item in groups.get(name, []):
                    result.extend(resolve(item, visited))
            else:
                result.append(name)
            return result

        return list(dict.fromkeys(resolve(selected_group_name)))

    def _get_mapped_config_value(
        self,
        section_name: str,
        mapping_key: str,
        value_key: str,
    ) -> Optional[str]:
        cfg = self.full_config.get(section_name, {})
        mappings = cfg.get(mapping_key, [])
        cwd_str = str(Path.cwd().as_posix())

        for mapping in mappings:
            pattern = mapping.get("pattern")
            if pattern and re.search(pattern, cwd_str, re.IGNORECASE):
                value = mapping.get(value_key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    def _resolve_path_token(self, raw_path: str) -> Path:
        return self.config_manager.resolve_path_token(raw_path)

    def _get_skill_search_roots(self) -> List[Path]:
        resource_root = self.config_manager.resolve_resource_root()
        return self.config_manager.get_skill_search_roots(resource_root)

    def _get_plugin_search_roots(self) -> List[Path]:
        resource_root = self.config_manager.resolve_resource_root()
        return self.config_manager.get_plugin_search_roots(resource_root)

    def _get_hook_search_roots(self) -> List[Path]:
        resource_root = self.config_manager.resolve_resource_root()
        return self.config_manager.get_hook_search_roots(resource_root)

    def get_current_project_group(self) -> str:
        return self.config_manager.get_current_project_group()

    def get_skills_to_mount(self) -> List[str]:
        """Retrieves the list of skill names to be mounted for the current project.

        Returns:
            List[str]: A list of skill names.
        """
        project_type = self.get_current_project_group()
        return get_skills_to_mount(
            self.full_config, self.skill_scanner, project_type=project_type
        )

    def get_plugins_to_mount(self) -> List[Dict[str, Any]]:
        """Retrieves the list of plugins to be mounted for the current project.

        Returns:
            List[Dict[str, Any]]: A list of plugin metadata dictionaries.
        """
        project_type = self.get_current_project_group()
        plugins, warnings = get_plugins_to_mount(
            self.full_config, self.plugin_scanner, project_type=project_type
        )
        self._print_scan_warnings("Plugin Scanner", warnings)
        return plugins

    def get_prompts_to_inject(self) -> List[str]:
        """Retrieves the list of prompt groups to be injected for the current project.

        Returns:
            List[str]: A list of prompt group names.
        """
        project_type = self.get_current_project_group()
        prompts, warnings = get_prompts_to_inject(
            self.full_config, self.prompt_scanner, project_type=project_type
        )
        self._print_scan_warnings("Prompt Scanner", warnings)
        return prompts

    def get_hooks_to_inject(self) -> List[Dict[str, Any]]:
        """Retrieves the list of hooks to be injected for the current project.

        Returns:
            List[Dict[str, Any]]: A list of hook metadata dictionaries.
        """
        project_type = self.get_current_project_group()
        hooks, warnings = get_hooks_to_inject(
            self.full_config, self.hook_scanner, project_type=project_type
        )
        self._print_scan_warnings("Hook Scanner", warnings)
        return hooks

    def _print_scan_warnings(self, scanner_name: str, warnings: List[str]) -> None:
        """Prints non-fatal scan warnings so they are visible to the user."""
        for warning in warnings:
            print(f"⚠️ {scanner_name}: {warning}")

    def assemble_prompt(self, task: str | None = None, is_review: bool = False) -> str:
        """Assembles the final system prompt by combining base prompts and injected groups.

        Args:
            task (str | None): The current task description.
            is_review (bool): Whether to assemble a review-specific prompt.

        Returns:
            str: The assembled prompt string.
        """
        groups = self.get_prompts_to_inject()
        prompt_fn = cast(
            Callable[..., str], prompt_review if is_review else prompt_general
        )

        return prompt_fn(
            task=task,
            groups=groups,
            prompt_root=self.prompt_scanner.prompt_root,
        )

    def write_temp_prompt(self, prompt: str) -> str:
        """Writes the assembled prompt to a temporary file in the project root.

        Args:
            prompt (str): The full prompt string to write.

        Returns:
            str: A guidance message for the agent on how to load the prompt.
        """
        prompt_dir = Path(tempfile.gettempdir()) / "codeagent-prompts"
        prompt_dir.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            dir=prompt_dir, prefix="ca_prompt.", suffix=".tmp", text=True
        )
        temp_file_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(prompt)
        except Exception:
            temp_file_path.unlink(missing_ok=True)
            raise
        if not hasattr(self, "_temp_prompt_paths"):
            self._temp_prompt_paths = set()
        self._temp_prompt_paths.add(temp_file_path)

        abs_path = str(temp_file_path.absolute()).replace("\\", "/")
        read_cmd = "Get-Content" if os.name == "nt" else "cat"

        return (
            f"IMPORTANT: The engineering standards for this session are in the CodeAgent file: {abs_path}. "
            f"Please use your 'run_shell_command' (e.g., '{read_cmd}') to load this file IMMEDIATELY. "
            f"**CRITICAL**: If searching for 'IMPLEMENTATION_PLAN.md' or other core files, be aware they may be listed in '.gitignore'. "
            f"You MUST use 'read_file' directly or set 'no_ignore=true' in search tools to find them."
        )

    def cleanup_temp_prompt(self):
        """Removes temporary prompt files created by this engine instance."""
        paths: set[Path] = getattr(self, "_temp_prompt_paths", set())
        for temp_file_path in list(paths):
            temp_file_path.unlink(missing_ok=True)
            paths.discard(temp_file_path)

    def acquire_resource_lock(self, lock_path: Path) -> BinaryIO:
        return self.lock_manager.acquire_resource_lock(lock_path)

    def release_resource_lock(self, handle: BinaryIO) -> None:
        self.lock_manager.release_resource_lock(handle)

    def run_shell(self, cmd: List[str], env: dict):
        """Executes a command in a subprocess with the given environment.

        Args:
            cmd (List[str]): The command and its arguments as a list of strings.
            env (dict): A dictionary of environment variables.

        Raises:
            FileNotFoundError: If the command executable cannot be found.
            SystemExit: If the command returns a non-zero exit code.
        """
        resolved_cmd = list(cmd)
        executable = shutil.which(resolved_cmd[0], path=env.get("PATH"))
        if executable:
            resolved_cmd[0] = executable

        try:
            result = subprocess.run(resolved_cmd, env=env, check=False)
        except FileNotFoundError:
            print(f"❌ Command not found: {cmd[0]}", file=sys.stderr)
            raise

        if result.returncode:
            raise SystemExit(result.returncode)

    def ensure_skills_link(self, target_link_path: str):
        link_path = (Path.cwd() / target_link_path).absolute()

        skills_to_mount = self.get_skills_to_mount()
        if not skills_to_mount:
            self.link_manager.cleanup_link_dir(link_path)
            return

        skill_roots = self._get_skill_search_roots()

        resolved_skills: List[tuple[str, Path]] = []
        resolved_skill_names = set()

        def append_resolved_skill(target_name: str, skill_src: Path):
            if target_name in resolved_skill_names:
                print(
                    f"ℹ️ Skip duplicate skill '{target_name}', "
                    f"keeping higher-priority source and ignoring: {skill_src}"
                )
                return
            resolved_skill_names.add(target_name)
            resolved_skills.append((target_name, skill_src))

        for skill_name in skills_to_mount:
            skill_src = None
            for root in skill_roots:
                candidate = (root / skill_name).resolve()
                if candidate.exists():
                    skill_src = candidate
                    break

            if skill_src:
                if skill_src.is_dir() and not (skill_src / "SKILL.md").exists():
                    for sub_item in skill_src.iterdir():
                        if sub_item.is_dir() and (sub_item / "SKILL.md").exists():
                            append_resolved_skill(sub_item.name, sub_item)
                else:
                    append_resolved_skill(skill_name.split("/")[-1], skill_src)
            else:
                searched = ", ".join(str(root / skill_name) for root in skill_roots)
                print(
                    f"⚠️ Warning: Skill '{skill_name}' not found. Searched: {searched}"
                )

        if not resolved_skills:
            searched_roots = ", ".join(str(root) for root in skill_roots)
            print(
                "⚠️ Warning: No mountable skills were resolved. "
                "Matched skill groups exist, but none of the candidate directories contain a valid SKILL.md. "
                f"Search roots: {searched_roots}"
            )
            self.link_manager.cleanup_link_dir(link_path)
            return

        print(
            f"🛠️  Skills matched group: [{self.get_current_project_group()}] "
            f"(匹配 {len(skills_to_mount)} 个根目录，挂载 {len(resolved_skills)} 个技能)"
        )
        link_path.mkdir(parents=True, exist_ok=True)

        desired_names = {target_name for target_name, _ in resolved_skills}
        self.link_manager.remove_stale_managed_links(link_path, desired_names)

        for target_name, skill_src in resolved_skills:
            target_skill_path = link_path / target_name
            try:
                self.link_manager.ensure_managed_link(skill_src, target_skill_path, link_path)
            except Exception as e:
                print(f"⚠️ Failed to link skill '{target_name}': {e}")

    def _get_plugin_link_dir(self) -> Optional[Path]:
        """Returns the directory where this engine's plugin links should be created.

        Each engine must override this to return its specific plugin directory:
        - Gemini:   ~/.gemini/extensions/
        - Codex:    ~/.codex/plugins/
        - Claude:   <cwd>/.claude/plugins/
        - OpenCode: <cwd>/.opencode/plugins/

        Returns:
            Optional[Path]: The absolute path to the plugin link directory,
                or None if plugins are not supported for this engine.
        """
        return None

    def ensure_plugins_link(self):
        plugins_to_mount = self.get_plugins_to_mount()
        link_dir = self._get_plugin_link_dir()
        if link_dir is None:
            return
        if not plugins_to_mount:
            self.link_manager.cleanup_link_dir(link_dir)
            return
        link_dir.mkdir(parents=True, exist_ok=True)
        desired_names = {
            str(plugin_meta.get("name"))
            for plugin_meta in plugins_to_mount
            if plugin_meta.get("name")
        }
        self.link_manager.remove_stale_managed_links(link_dir, desired_names)

        mounted_count = 0
        for plugin_meta in plugins_to_mount:
            plugin_name = plugin_meta["name"]
            plugin_src_str = plugin_meta.get("_plugin_dir")

            if not plugin_src_str:
                continue

            plugin_src = Path(plugin_src_str).resolve()
            target_link = link_dir / plugin_name

            try:
                if self.link_manager.ensure_managed_link(plugin_src, target_link, link_dir):
                    mounted_count += 1
            except Exception as e:
                print(f"⚠️ Failed to link plugin '{plugin_name}': {e}")

        if mounted_count:
            print(f"🔌 Ensured {mounted_count} plugin links in {link_dir}")

    def cleanup_plugins_link(self):
        link_dir = self._get_plugin_link_dir()
        if link_dir is None:
            return
        self.link_manager.cleanup_link_dir(link_dir)

    def _create_skill_link(self, source: Path, target: Path):
        self.link_manager.create_skill_link(source, target)

    def _safe_remove_link(self, path: Path):
        if not path.exists() and not path.is_symlink():
            return

        if not (self._is_windows_link(path) or path.is_symlink()):
            print(f"⚠️ Refusing to remove unmanaged path: {path}")
            return

        try:
            if os.name == "nt":
                if path.is_dir():
                    subprocess.run(
                        ["cmd", "/c", "rmdir", str(path)],
                        capture_output=True,
                        check=False,
                    )
                else:
                    path.unlink(missing_ok=True)
            else:
                path.unlink(missing_ok=True)
        except Exception as e:
            print(f"⚠️ Security: Failed to remove link {path}: {e}")

    _LINK_MANIFEST = ".codeagent-links.json"

    def _load_link_manifest(self, link_path: Path) -> dict[str, str]:
        return self.link_manager.load_manifest(link_path)

    def _save_link_manifest(self, link_path: Path, manifest: dict[str, str]) -> None:
        self.link_manager.save_manifest(link_path, manifest)

    def _managed_link_matches(self, path: Path, source: Path) -> bool:
        return self.link_manager.managed_link_matches(path, source)

    def _ensure_managed_link(self, source: Path, target: Path, link_path: Path) -> bool:
        return self.link_manager.ensure_managed_link(source, target, link_path)

    def _remove_stale_managed_links(
        self, link_path: Path, desired_names: set[str]
    ) -> None:
        self.link_manager.remove_stale_managed_links(link_path, desired_names)

    def _cleanup_link_dir(self, link_path: Path):
        self.link_manager.cleanup_link_dir(link_path)

    def cleanup_skills_link(self, target_link_path: str):
        self.link_manager.cleanup_link_dir((Path.cwd() / target_link_path).absolute())

    def _is_windows_link(self, path: Path) -> bool:
        from core.link_manager import is_windows_link
        return is_windows_link(path)

    def inject_hooks_to_settings(
        self, settings_rel_path: str, hooks: List[Dict[str, Any]]
    ):
        settings_path = (Path.cwd() / settings_rel_path).absolute()
        self.settings_manager.inject_hooks(settings_path, hooks)
        if hooks:
            print(f"✅ Injected {len(hooks)} hooks into {settings_rel_path}")

    def inject_plugins_to_settings(self, settings_rel_path: str):
        """Orchestrates the injection of plugin configurations into a settings file.

        Manages backups and delegates loading, formatting, and saving to helper methods.

        Args:
            settings_rel_path (str): Relative path to the settings file.
        """
        plugins = self.get_plugins_to_mount()
        if not plugins:
            return

        settings_path = (Path.cwd() / settings_rel_path).absolute()
        settings_path.parent.mkdir(parents=True, exist_ok=True)

        backup_path = settings_path.with_suffix(settings_path.suffix + ".bak")
        if settings_path.exists() and not backup_path.exists():
            shutil.copy2(settings_path, backup_path)
            print(f"💾 Created safety backup: {backup_path.name}")

        data = self._load_config(settings_path)
        data["_ca_injected"] = True

        data = self._format_plugins_for_settings(data, plugins)

        self._save_config(settings_path, data)

        print(f"✅ Registered plugins in {settings_rel_path}")

    def _load_config(self, path: Path) -> Any:
        """Loads a configuration file.

        Default implementation handles JSON. Subclasses can override for other formats.

        Args:
            path (Path): The path to the configuration file.

        Returns:
            Any: The loaded configuration data.
        """
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_config(self, path: Path, data: Any):
        """Saves configuration data to a file.

        Default implementation handles JSON.

        Args:
            path (Path): The path to the configuration file.
            data (Any): The data to save.
        """
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _format_plugins_for_settings(self, data: Any, plugins: List[dict]) -> Any:
        """Formats plugin metadata for the specific engine's settings.

        Args:
            data (Any): The existing configuration data.
            plugins (List[dict]): The list of plugins to format.

        Returns:
            Any: The updated configuration data with plugins registered.
        """
        return data

    def restore_settings(self, settings_rel_path: str):
        settings_path = (Path.cwd() / settings_rel_path).absolute()
        self.settings_manager.restore_settings(settings_path)

    def execute(self, message: str, model: str, non_interactive: bool = False):
        """Abstract method to execute a message with the LLM engine.

        Args:
            message (str): The message or prompt to send.
            model (str): The model name to use.
            non_interactive (bool): Whether to run in non-interactive mode.

        Raises:
            NotImplementedError: Must be implemented by subclasses.
        """
        raise NotImplementedError
