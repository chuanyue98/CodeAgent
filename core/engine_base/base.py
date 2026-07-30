from core.config_manager import ConfigManager
from core.engine_base.config_mixin import _ConfigMixin
from core.engine_base.environment import EnvironmentManager
from core.engine_base.links_mixin import _LinksMixin
from core.engine_base.prompt_mixin import _PromptMixin
from core.engine_base.settings_mixin import _SettingsMixin
from core.hook_scanner import HookScanner
from core.link_manager import LinkManager
from core.lock_manager import LockManager
from core.plugin_scanner import PluginScanner
from core.prompt_scanner import PromptScanner
from core.resource_locator import CODE_ROOT
from core.settings_manager import SettingsManager
from core.skill_scanner import SkillScanner


class BaseEngine(_ConfigMixin, _PromptMixin, _LinksMixin, _SettingsMixin):
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
        self.root_dir = CODE_ROOT
        self.config_manager = ConfigManager(self.root_dir)
        self.full_config = self.config_manager.full_config
        self.env_manager = EnvironmentManager(self.root_dir)
        self._temp_prompt_paths: set = set()
        self.link_manager = LinkManager()
        self.lock_manager = LockManager()
        self.settings_manager = SettingsManager(self.EVENT_MAP)
        resource_root = self.config_manager.resolve_resource_root()
        self.skill_scanner = SkillScanner(resource_root / "skills")
        self.prompt_scanner = PromptScanner(resource_root / "prompt")
        self.hook_scanner = HookScanner(
            self.config_manager.get_hook_search_roots(resource_root)
        )
        self.plugin_scanner = PluginScanner(resource_root / "plugins")

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
