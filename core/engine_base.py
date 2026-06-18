#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

from core.hook_scanner import HookScanner, get_hooks_to_inject
from core.plugin_scanner import PluginScanner, get_plugins_to_mount
from core.prompt_kit import prompt_general, prompt_review
from core.prompt_scanner import PromptScanner, get_prompts_to_inject
from core.services.config_service import ConfigService
from core.skill_scanner import SkillScanner, get_skills_to_mount


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
        self.full_config = self._load_full_config()
        self.env_manager = EnvironmentManager(self.root_dir)
        self.temp_prompt_name = ".ca_prompt.tmp"
        resource_root = self._resolve_resource_root()
        self.skill_scanner = SkillScanner(resource_root / "skills")
        self.prompt_scanner = PromptScanner(resource_root / "prompt")
        self.hook_scanner = HookScanner(self._get_hook_search_roots())
        self.plugin_scanner = PluginScanner(resource_root / "plugins")

    def _resolve_resource_root(self) -> Path:
        """Returns the resource root directory, respecting resource_root in config.json."""
        resource_root = self.full_config.get("paths", {}).get("resource_root")
        if resource_root:
            expanded = str(resource_root).replace(
                "$CODEAGENT", self.root_dir.as_posix()
            )
            resource_path = Path(expanded).expanduser()
            resolved = (
                resource_path
                if resource_path.is_absolute()
                else self.root_dir / resource_path
            ).resolve()
            if resolved.is_dir():
                return resolved
        return self.root_dir

    def _load_full_config(self) -> dict:
        """Loads the complete configuration using ConfigService.

        Returns:
            dict: The loaded configuration dictionary, or an empty dict if not found or invalid.
        """
        config_service = ConfigService(self.root_dir / "config.json")
        config, _ = config_service.get_config()
        return config

    def _resolve_config_groups(self, section_name: str) -> List[str]:
        """Resolves configuration groups based on the current working directory.

        It matches the current directory against patterns defined in the configuration
        and resolves any nested group references.

        Args:
            section_name (str): The configuration section to resolve (e.g., 'skills', 'prompts').

        Returns:
            List[str]: A list of resolved item names belonging to the matched group.
        """
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

        return list(set(resolve(selected_group_name)))

    def _get_mapped_config_value(
        self,
        section_name: str,
        mapping_key: str,
        value_key: str,
    ) -> Optional[str]:
        """Retrieves a specific configuration value based on project path mapping.

        Args:
            section_name (str): The configuration section.
            mapping_key (str): The key containing the mapping list.
            value_key (str): The key for the value to retrieve from the matched mapping.

        Returns:
            Optional[str]: The mapped value if found, otherwise None.
        """
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
        """Resolves path tokens ($CWD, $CODEAGENT) in a raw path string.

        Args:
            raw_path (str): The path string potentially containing tokens.

        Returns:
            Path: The resolved absolute Path object.
        """
        expanded = raw_path.replace("$CWD", str(Path.cwd().as_posix()))
        expanded = expanded.replace("$CODEAGENT", str(self.root_dir.as_posix()))
        path_obj = Path(expanded)
        if path_obj.is_absolute():
            return path_obj
        return (self.root_dir / path_obj).resolve()

    def _get_skill_search_roots(self) -> List[Path]:
        """Identifies all root directories where skills should be searched.

        This includes the default skills directory, any project-specific skill roots
        defined in config.json, and the 'skills' directory in the current working directory.

        Returns:
            List[Path]: A list of absolute paths to skill search roots.
        """
        skill_path_cfg = self.full_config.get("paths", {}).get("skills", "skills")
        default_root = (self.root_dir / skill_path_cfg).resolve()

        cfg = self.full_config.get("skills", {})
        mappings = cfg.get("project_skill_root_mapping", [])
        cwd = Path.cwd().resolve()
        cwd_str = str(cwd.as_posix())

        roots = []
        for mapping in mappings:
            pattern = mapping.get("pattern")
            if pattern and re.search(pattern, cwd_str, re.IGNORECASE):
                mapped_path = mapping.get("path")
                if mapped_path:
                    roots.append(self._resolve_path_token(mapped_path).resolve())

        if cwd != self.root_dir.resolve():
            project_skills = cwd / "skills"
            if project_skills.is_dir():
                if project_skills.resolve() not in roots:
                    roots.append(project_skills.resolve())

        if default_root not in roots:
            roots.append(default_root)

        return roots

    def _get_plugin_search_roots(self) -> List[Path]:
        """Identifies all root directories where plugins should be searched.

        This includes the default plugins directory and the 'plugins' directory
        in the current working directory.

        Returns:
            List[Path]: A list of absolute paths to plugin search roots.
        """
        plugin_path_cfg = self.full_config.get("paths", {}).get("plugins", "plugins")
        default_root = (self._resolve_resource_root() / plugin_path_cfg).resolve()

        roots = []
        cwd = Path.cwd().resolve()

        if cwd != self.root_dir.resolve():
            project_plugins = cwd / "plugins"
            if project_plugins.is_dir():
                roots.append(project_plugins.resolve())

        if default_root not in roots:
            roots.append(default_root)

        return roots

    def _get_hook_search_roots(self) -> List[Path]:
        """Identifies all root directories where hooks should be searched.

        This includes the default hooks directory and the 'hooks' directory
        in the current working directory.

        Returns:
            List[Path]: A list of absolute paths to hook search roots.
        """
        hook_path_cfg = self.full_config.get("paths", {}).get("hooks", "hooks")
        default_root = (self._resolve_resource_root() / hook_path_cfg).resolve()

        roots = []
        cwd = Path.cwd().resolve()

        if cwd != self.root_dir.resolve():
            project_hooks = cwd / "hooks"
            if project_hooks.is_dir():
                roots.append(project_hooks.resolve())

        if default_root not in roots:
            roots.append(default_root)

        return roots

    def get_current_project_group(self) -> str:
        """Determines the unified project group name for the current working directory.

        It first checks if the CWD is within CodeAgent itself. If not, it attempts
         to match the CWD against the 'project_registry' in config.json.

        Returns:
            str: The matched group name (e.g., 'codeagent', 'some-project'),
                 or the default group if no match is found.
        """
        explicit_group = os.environ.get("CA_PROJECT_GROUP", "").strip()
        if explicit_group:
            return explicit_group

        cwd = Path.cwd().resolve()
        root = self.root_dir.resolve()

        if cwd == root or root in cwd.parents:
            return "codeagent"

        registry = self.full_config.get("project_registry", [])
        best_match_group = None
        max_match_len = -1

        for item in registry:
            raw_path = item.get("path")
            if not raw_path:
                continue

            try:
                mapping_path = Path(raw_path).resolve()
                if cwd == mapping_path or mapping_path in cwd.parents:
                    match_len = len(str(mapping_path.as_posix()))
                    if match_len > max_match_len:
                        max_match_len = match_len
                        best_match_group = item.get("group")
            except Exception:
                continue

        return best_match_group or self.full_config.get("default_group", "common")

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
        temp_file_path = self.root_dir / self.temp_prompt_name
        temp_file_path.write_text(prompt, encoding="utf-8")

        abs_path = str(temp_file_path.absolute()).replace("\\", "/")
        read_cmd = "Get-Content" if os.name == "nt" else "cat"

        return (
            f"IMPORTANT: The engineering standards for this session are in the CodeAgent file: {abs_path}. "
            f"Please use your 'run_shell_command' (e.g., '{read_cmd}') to load this file IMMEDIATELY. "
            f"**CRITICAL**: If searching for 'IMPLEMENTATION_PLAN.md' or other core files, be aware they may be listed in '.gitignore'. "
            f"You MUST use 'read_file' directly or set 'no_ignore=true' in search tools to find them."
        )

    def cleanup_temp_prompt(self):
        """Removes the temporary prompt file from the project root."""
        temp_file_path = self.root_dir / self.temp_prompt_name
        if temp_file_path.exists():
            temp_file_path.unlink()

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
        """Ensures that skill links are created in the target directory.

        It resolves the skills to be mounted based on the current project group,
        cleans up any existing stale links, and creates new symlinks or junctions.

        Args:
            target_link_path (str): The relative path to the directory where skills should be linked.
        """
        link_path = (Path.cwd() / target_link_path).absolute()
        self._cleanup_link_dir(link_path)

        skills_to_mount = self.get_skills_to_mount()
        if not skills_to_mount:
            return

        skill_roots = self._get_skill_search_roots()

        resolved_skills: List[Tuple[str, Path]] = []
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
            return

        print(
            f"🛠️  Skills matched group: [{self.get_current_project_group()}] "
            f"(匹配 {len(skills_to_mount)} 个根目录，挂载 {len(resolved_skills)} 个技能)"
        )
        link_path.mkdir(parents=True, exist_ok=True)

        for target_name, skill_src in resolved_skills:
            target_skill_path = link_path / target_name
            if target_skill_path.exists():
                self._safe_remove_link(target_skill_path)

            try:
                self._create_skill_link(skill_src, target_skill_path)
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
        """Ensures that plugin links exist in the engine's plugin directory.

        Uses a 'stable mapping' strategy: if a link already points to the correct
        source, it is not recreated. Stale links are removed and recreated.
        No-op if ``_get_plugin_link_dir()`` returns None.
        """
        plugins_to_mount = self.get_plugins_to_mount()
        if not plugins_to_mount:
            return

        link_dir = self._get_plugin_link_dir()
        if link_dir is None:
            return
        link_dir.mkdir(parents=True, exist_ok=True)

        mounted_count = 0
        for plugin_meta in plugins_to_mount:
            plugin_name = plugin_meta["name"]
            plugin_src_str = plugin_meta.get("_plugin_dir")

            if not plugin_src_str:
                continue

            plugin_src = Path(plugin_src_str).resolve()
            target_link = link_dir / plugin_name

            if target_link.exists():
                try:
                    if self._is_windows_link(target_link) or target_link.is_symlink():
                        if target_link.resolve() == plugin_src:
                            continue
                        else:
                            self._safe_remove_link(target_link)
                    else:
                        print(
                            f"⚠️ Warning: '{plugin_name}' exists as a real directory in global exts. Skipping."
                        )
                        continue
                except Exception:
                    self._safe_remove_link(target_link)

            try:
                self._create_skill_link(plugin_src, target_link)
                mounted_count += 1
            except Exception as e:
                print(f"⚠️ Failed to link plugin '{plugin_name}': {e}")

        if mounted_count:
            print(f"🔌 Ensured {mounted_count} plugin links in {link_dir}")

    def cleanup_plugins_link(self):
        """Removes plugin links from the engine's plugin directory.

        Only removes items verified to be links (symlinks or Windows junctions).
        No-op if ``_get_plugin_link_dir()`` returns None.
        """
        plugins_to_mount = self.get_plugins_to_mount()
        if not plugins_to_mount:
            return

        link_dir = self._get_plugin_link_dir()
        if link_dir is None:
            return
        for plugin_meta in plugins_to_mount:
            plugin_name = plugin_meta["name"]
            target_link = link_dir / plugin_name

            if self._is_windows_link(target_link) or target_link.is_symlink():
                self._safe_remove_link(target_link)

    def _create_skill_link(self, source: Path, target: Path):
        """Creates a symbolic link or Windows junction from source to target.

        Args:
            source (Path): The source directory or file.
            target (Path): The target link path.

        Raises:
            subprocess.CalledProcessError: If mklink fails on Windows.
            OSError: If symlink creation fails on other platforms.
        """
        try:
            target.symlink_to(source, target_is_directory=source.is_dir())
            return
        except OSError:
            if os.name != "nt" or not source.is_dir():
                raise

        subprocess.run(
            ["cmd", "/c", "mklink", "/j", str(target), str(source)],
            capture_output=True,
            check=True,
        )

    def _safe_remove_link(self, path: Path):
        """Safely removes a link without affecting the target content.

        Handles both standard symlinks and Windows junctions.

        Args:
            path (Path): The path to the link to remove.
        """
        if not path.exists() and not path.is_symlink():
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

    def _cleanup_link_dir(self, link_path: Path):
        """Cleans up stale links within a directory while preserving other files.

        Args:
            link_path (Path): The directory to clean up.
        """
        if not link_path.exists():
            return

        try:
            for item in list(link_path.iterdir()):
                if self._is_windows_link(item) or item.is_symlink():
                    self._safe_remove_link(item)

            if not any(link_path.iterdir()):
                link_path.rmdir()
        except Exception:
            pass

    def cleanup_skills_link(self, target_link_path: str):
        """Cleans up injected skill links in the specified directory.

        Args:
            target_link_path (str): The relative path to the directory containing skill links.
        """
        self._cleanup_link_dir((Path.cwd() / target_link_path).absolute())

    def _is_windows_link(self, path: Path) -> bool:
        """Verifies if a path is a Windows link or junction point.

        Uses multiple checks including symlink status, reparse point attributes,
        and mount point status.

        Args:
            path (Path): The path to check.

        Returns:
            bool: True if it's a Windows link/junction, False otherwise.
        """
        try:
            if path.is_symlink():
                return True

            stat_info = path.lstat()
            attrs = getattr(stat_info, "st_file_attributes", 0)
            is_reparse = bool(attrs & 1024)

            if is_reparse:
                return True

            if path.is_mount():
                return True

            return False
        except Exception:
            return False

    def inject_hooks_to_settings(
        self, settings_rel_path: str, hooks: List[Dict[str, Any]]
    ):
        """Injects hook configurations into a settings file (e.g., .gemini/settings.json).

        Creates a backup of the settings file if it doesn't already exist.

        Args:
            settings_rel_path (str): Relative path to the settings file.
            hooks (List[Dict[str, Any]]): List of hook metadata dictionaries.
        """
        if not hooks:
            return

        settings_path = (Path.cwd() / settings_rel_path).absolute()
        settings_path.parent.mkdir(parents=True, exist_ok=True)

        backup_path = settings_path.with_suffix(".json.bak")
        if settings_path.exists() and not backup_path.exists():
            shutil.copy2(settings_path, backup_path)
            print(f"💾 Created safety backup: {backup_path.name}")

        data = {}
        if settings_path.exists():
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        if "hooks" not in data:
            data["hooks"] = {}

        data["_ca_injected"] = True

        for hook in hooks:
            event_name = hook.get("event")
            if not event_name:
                continue
            event = self.EVENT_MAP.get(event_name, event_name)
            if event not in data["hooks"]:
                data["hooks"][event] = [{"matcher": "*", "hooks": []}]

            target_group = next(
                (g for g in data["hooks"][event] if g.get("matcher") == "*"), None
            )
            if not target_group:
                target_group = {"matcher": "*", "hooks": []}
                data["hooks"][event].append(target_group)

            event_hooks = target_group["hooks"]
            existing = next(
                (h for h in event_hooks if h.get("name") == hook["name"]), None
            )

            hook_entry = {
                "name": hook["name"],
                "type": "command",
                "command": hook["command"],
            }

            if existing:
                existing.update(hook_entry)
            else:
                event_hooks.append(hook_entry)

        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

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
        """Restores a settings file from its backup or removes it if it was newly created.

        Args:
            settings_rel_path (str): Relative path to the settings file to restore.
        """
        settings_path = (Path.cwd() / settings_rel_path).absolute()
        backup_path = settings_path.with_suffix(settings_path.suffix + ".bak")

        if backup_path.exists():
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(str(backup_path), str(settings_path))
            print(f"♻️ Restored {settings_rel_path} from backup")
            return

        if settings_path.exists():
            try:
                data = self._load_config(settings_path)
                if isinstance(data, dict) and data.get("_ca_injected") is True:
                    settings_path.unlink()
                    print(f"♻️ Removed injected {settings_rel_path}")
            except Exception:
                pass

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
