"""CLI, launcher and command output translations."""

CLI_MESSAGES: dict[str, dict[str, str]] = {
    "project.unregistered_hint": {
        "en": "i  {cwd} is not registered to a resource group; running with "
        "defaults.\n"
        "   To register: ca project add {cwd} --group <group-name>",
        "zh": "i  {cwd} 尚未注册到任何资源组，本次将使用默认设置运行。\n"
        "   如需注册: ca project add {cwd} --group <group-name>",
    },
    "project.unregistered_title": {
        "en": "\n[*] Current directory is not registered to a resource group: {cwd}",
        "zh": "\n[*] 当前目录尚未注册到任何资源组: {cwd}",
    },
    "project.pick_group": {
        "en": "Pick a resource group (future launches here load it automatically):",
        "zh": "请选择要绑定的资源组 (以后从这个目录启动会自动加载对应技能集):",
    },
    "project.new_group_option": {
        "en": "  n. Create a new group",
        "zh": "  n. 新建资源组",
    },
    "project.skip_option": {
        "en": "  <enter>. Skip (use defaults this time, nothing written)",
        "zh": "  直接回车. 跳过 (本次使用默认组, 不写入配置)",
    },
    "project.new_group_prompt": {"en": "New group name: ", "zh": "新组名称: "},
    "project.no_group_name": {
        "en": "[!] No group name entered; skipping registration.",
        "zh": "[!] 未输入组名, 跳过注册。",
    },
    "project.invalid_choice": {
        "en": "[!] Invalid input; skipping registration.",
        "zh": "[!] 无效输入, 跳过注册。",
    },
    "project.registered": {
        "en": "[OK] Registered the current directory to group [{group}]\n",
        "zh": "[OK] 已将当前目录注册到组 [{group}]\n",
    },
    "proxy.enabled": {
        "en": "Proxy enabled: {scheme}://{host}:{port}",
        "zh": "代理已启用: {scheme}://{host}:{port}",
    },
    "task.authoring_start": {
        "en": "Starting the task-authoring expert to draft: {name}...",
        "zh": "启动任务编排专家为您编写新任务: {name}...",
    },
    "task.target_location": {"en": "Target location: {path}", "zh": "目标位置: {path}"},
    "task.authoring_engine": {
        "en": "Authoring with: {engine}",
        "zh": "本次由 {engine} 执笔",
    },
    "task.no_engine": {
        "en": "No engine CLI found on PATH, so there is nothing to author with.\n"
        "Install one (see `ca doctor`), or name it with `ca new <task> --engine "
        "<name>`.",
        "zh": "PATH 上没有找到任何引擎 CLI，没法写任务。\n"
        "先装一个 (可看 `ca doctor`)，或用 `ca new <任务名> --engine <引擎>` 指定。",
    },
    "task.authoring_prompt": {
        "en": "Enter 'Task Authoring' mode. Write a new automation task "
        "playbook for CodeAgent, in the file named: ",
        "zh": "请启动'任务编排专家 (Task Authoring)'模式，目标是为 CodeAgent "
        "编写一个新的自动化任务剧本，文件名为：",
    },
    "cli.help.task_mode": {"en": "Task mode", "zh": "任务模式"},
    "cli.help.list_tasks": {"en": "List all tasks", "zh": "列出所有任务"},
    "cli.help.non_interactive": {"en": "Non-interactive mode", "zh": "非交互模式"},
    "cli.help.yolo_default_on": {
        "en": "YOLO mode (on by default)",
        "zh": "开启 YOLO 模式 (默认开启)",
    },
    "cli.help.yolo_mode": {
        "en": "YOLO mode (bypass approvals/sandbox)",
        "zh": "开启 YOLO 模式 (跳过审批与沙箱)",
    },
    "cli.help.review_pr_url": {"en": "PR URL to review", "zh": "代码审查 PR URL"},
    "cli.epilog": {
        "en": "Engines: opencode, claude, codex, codebuddy, antigravity (agy)\n"
        "\n"
        "YOLO mode is enabled by default.\n"
        "\n"
        "\x08\n"
        "Examples:\n"
        "  ca                       Open interactive launcher console (in terminal)\n"
        "  ca menu                  Same as bare ca\n"
        "  ca claude                Start Claude Code\n"
        "  ca codex                 Start OpenAI Codex\n"
        "  ca opencode              Start OpenCode\n"
        "  ca agy                   Start Google Antigravity\n"
        "  ca -r                    List and resume recent sessions across all "
        "engines\n"
        "  ca -r 2                  Resume the 2nd most recent session directly\n"
        "  ca resume                Same as ca -r (supports --engine <name>)\n"
        "  ca -s                    Switch a session to another engine "
        "interactively\n"
        "  ca -s codex              Switch current session to Codex (Enter to "
        "confirm)\n"
        "  ca -s codex 2            Switch the 2nd listed session to Codex directly\n"
        "  ca switch codex          Same as ca -s codex\n"
        "  ca status                Show current project, group, and standards "
        "status\n"
        "  ca doctor --fix          Run health check and auto-repair\n"
        "  ca ui                    Start the Web UI\n",
        "zh": "引擎: opencode, claude, codex, codebuddy, antigravity (agy)\n"
        "\n"
        "YOLO 模式默认开启。\n"
        "\n"
        "\x08\n"
        "示例:\n"
        "  ca                       打开交互式启动菜单\n"
        "  ca menu                  同上\n"
        "  ca claude                启动 Claude Code\n"
        "  ca codex                 启动 OpenAI Codex\n"
        "  ca opencode              启动 OpenCode\n"
        "  ca agy                   启动 Google Antigravity\n"
        "  ca -r                    列出并接力最近的会话 (跨所有引擎)\n"
        "  ca -r 2                  直接接力列表里的第 2 条\n"
        "  ca resume                同 ca -r (支持 --engine <引擎>)\n"
        "  ca -s                    交互式把会话接力到另一个引擎\n"
        "  ca -s codex              把当前会话接力到 Codex (回车确认)\n"
        "  ca -s codex 2            直接把列表里的第 2 条接力到 Codex\n"
        "  ca switch codex          同 ca -s codex\n"
        "  ca status                看当前项目、资源组与规范的状态\n"
        "  ca doctor --fix          体检环境并自动修复\n"
        "  ca ui                    启动 Web UI\n",
    },
    "cli.desc.root": {
        "en": "CodeAgent: Professional AI Engineering Shell.",
        "zh": "CodeAgent: 专业的 AI 工程外壳。",
    },
    "cli.help.proxy": {
        "en": "Enable proxy from config.json",
        "zh": "启用 config.json 中配置的代理",
    },
    "cli.help.yolo": {
        "en": "Enable YOLO mode (bypass sandbox and approvals)",
        "zh": "开启 YOLO 模式 (跳过沙箱与审批)",
    },
    "cli.help.resume": {
        "en": "Resume a previous session (list sessions or pass index/ID)",
        "zh": "接力之前的会话 (不带参数列出会话，也可传编号或 ID)",
    },
    "cli.help.resume_engine": {
        "en": "Filter sessions by engine when resuming",
        "zh": "接力时只看这个引擎的会话",
    },
    "cli.help.interactive": {
        "en": "Launch interactive console menu",
        "zh": "打开交互式控制台菜单",
    },
    "cli.desc.menu": {
        "en": "Open the interactive launcher console",
        "zh": "打开交互式启动菜单",
    },
    "cli.desc.status": {
        "en": "Show what CodeAgent is currently doing for you.",
        "zh": "看一眼 CodeAgent 此刻正在为你做什么。",
    },
    "cli.desc.ps": {
        "en": "List background task runs.",
        "zh": "列出后台任务的运行情况。",
    },
    "cli.help.ps_all": {
        "en": "Include completed/failed/stopped runs, not just running ones",
        "zh": "连同已完成/失败/已停止的一起列出，而不只是运行中的",
    },
    "cli.desc.stop": {
        "en": "Stop a running background task.",
        "zh": "停掉一个正在跑的后台任务。",
    },
    "cli.desc.batch_run": {
        "en": "Run TASK_NAME once in every registered project.",
        "zh": "把 TASK_NAME 这个任务在所有已登记的项目里各跑一遍。",
    },
    "cli.help.batch_engine": {
        "en": "Engine to run the task with in every target project.",
        "zh": "在每个目标项目里用哪个引擎跑这个任务。",
    },
    "cli.help.batch_group": {
        "en": "Only target projects registered under this resource group "
        "(default: all registered projects).",
        "zh": "只跑登记在这个资源组下的项目 (默认: 所有已登记项目)。",
    },
    "cli.help.batch_dry_run": {
        "en": "List the projects that would run, without starting anything.",
        "zh": "只列出会被跑到的项目，不真的启动。",
    },
    "cli.desc.new": {
        "en": "Write a new task playbook with an engine's help.",
        "zh": "让引擎陪你写一个新的任务剧本。",
    },
    "cli.help.new_engine": {
        "en": "Engine to author the task with (default: the first one installed).",
        "zh": "用哪个引擎来写这个任务 (默认: 第一个装好的引擎)。",
    },
    "cli.desc.doctor": {
        "en": "Check the environment and repair what it can.",
        "zh": "体检运行环境，能修的顺手修掉。",
    },
    "cli.help.doctor_fix": {"en": "Auto-repair issues", "zh": "自动修复发现的问题"},
    "cli.help.doctor_dry_run": {
        "en": "Show what --fix would change, without making any changes",
        "zh": "只展示 --fix 会改什么，不真的改",
    },
    "cli.desc.ui": {"en": "Start the Web UI dashboard.", "zh": "启动 Web UI 面板。"},
    "cli.help.ui_show_token": {
        "en": "Print the Web UI token and exit, for opening the UI manually.",
        "zh": "只打印 Web UI 的访问令牌然后退出，方便手动打开页面。",
    },
    "cli.help.ui_dev": {
        "en": "Serve the frontend from a live-reloading Vite dev server instead of "
        "the built bundle, so frontend edits need no rebuild.",
        "zh": "前端走 Vite 开发服务器热更新，改前端不用重新构建。",
    },
    "cli.desc.switch": {
        "en": "Continue a session in TARGET_ENGINE (shorthand: `ca -s`).\n"
        "\n"
        "SELECTOR is the number `ca -r` / `ca history` printed, or a session "
        "id. Omit it to take the most recent session in this project.",
        "zh": "把一条会话接力到 TARGET_ENGINE 继续 (简写: `ca -s`)。\n"
        "\n"
        "SELECTOR 是 `ca -r` / `ca history` 列表里的编号，或会话 ID。不写就取这个项目最近的一条会话。",
    },
    "cli.help.switch_from": {
        "en": "Only consider sessions from this engine when picking the source.",
        "zh": "只从这个引擎的会话里挑接力来源。",
    },
    "cli.help.switch_yes": {
        "en": "Confirm the latest session without interactive prompt.",
        "zh": "不问了，直接用最近的那条会话。",
    },
    "cli.help.switch_no_launch": {
        "en": "Still converts (a new session is written), then prints the "
        "resume command instead of starting the engine.",
        "zh": "照常转换（会写出一条新会话），只是不启动引擎，改为打印接力命令。",
    },
    "cli.desc.resume_cmd": {
        "en": "Resume a previous session from this project across any engine.\n"
        "\n"
        "SELECTOR is an index (1, 2, ...) or session id. Omit it to see an "
        "interactive list of recent sessions, or press Enter to resume the "
        "most recent.",
        "zh": "接着这个项目之前的会话继续，跨引擎都行。\n"
        "\n"
        "SELECTOR 可以是编号 (1、2 ...) 或会话 ID。不写就会列出最近的会话让你挑，直接回车则接力最近的一条。",
    },
    "cli.help.resume_cmd_engine": {
        "en": "Filter by engine",
        "zh": "只看这个引擎的会话",
    },
    "cli.desc.project": {
        "en": "Manage the project registry (config.json's project_registry).",
        "zh": "管理项目登记表 (config.json 里的 project_registry)。",
    },
    "cli.desc.project_add": {
        "en": "Register PATH (default: the current directory) into a resource group.",
        "zh": "把 PATH (默认当前目录) 登记到某个资源组下。",
    },
    "cli.desc.project_remove": {
        "en": "Remove PATH from the project registry.",
        "zh": "把 PATH 从项目登记表里删掉。",
    },
    "cli.desc.project_list": {
        "en": "List every registered project and the group it is bound to.",
        "zh": "列出所有已登记的项目，以及各自绑定的资源组。",
    },
    "cli.help.project_group": {
        "en": "Resource group to bind this project to.",
        "zh": "把这个项目绑定到哪个资源组。",
    },
    "cli.desc.resources": {
        "en": "Discover skills, plugins, hooks, and prompts without opening the "
        "Web UI.",
        "zh": "不开 Web UI 也能查看技能、插件、钩子与规范。",
    },
    "cli.desc.resources_list": {
        "en": "List resources of KIND, marking which ones the group has enabled.",
        "zh": "列出 KIND 这一类资源，并标出哪些在该分组里已启用。",
    },
    "cli.help.resources_group": {
        "en": "Resource group to check the enabled/active state against.",
        "zh": "按哪个资源组判断启用状态。",
    },
    "cli.desc.mcp": {
        "en": "Inspect and sync MCP servers across engines.",
        "zh": "查看并在各引擎之间同步 MCP 服务。",
    },
    "cli.desc.mcp_list": {
        "en": "List configured MCP servers for ENGINE (default: all engines).",
        "zh": "列出 ENGINE 已配置的 MCP 服务 (默认: 所有引擎)。",
    },
    "cli.desc.mcp_add": {
        "en": "Add an MCP server named NAME to ENGINE.",
        "zh": "给 ENGINE 添加一个名为 NAME 的 MCP 服务。",
    },
    "cli.help.mcp_add_url": {
        "en": "Remote server URL, instead of a command.",
        "zh": "远程服务地址，用来替代本地命令。",
    },
    "cli.help.mcp_add_env": {
        "en": "Environment variable for the server; repeatable.",
        "zh": "传给该服务的环境变量，可重复指定。",
    },
    "cli.help.mcp_add_transport": {
        "en": "Transport for a --url server (e.g. http, sse). Ignored for stdio.",
        "zh": "--url 服务使用的传输方式 (如 http、sse)；stdio 时忽略。",
    },
    "cli.desc.mcp_remove": {
        "en": "Remove the MCP server named NAME from ENGINE.",
        "zh": "从 ENGINE 中删除名为 NAME 的 MCP 服务。",
    },
    "cli.desc.mcp_sync": {
        "en": "Copy SOURCE's MCP servers into the other engines.",
        "zh": "把 SOURCE 的 MCP 服务复制到其他引擎。",
    },
    "cli.help.mcp_sync_to": {
        "en": "Target engine; repeatable. Defaults to every engine but SOURCE.",
        "zh": "目标引擎，可重复指定；默认是除 SOURCE 外的所有引擎。",
    },
    "cli.help.mcp_sync_name": {
        "en": "Only sync this server; repeatable. Defaults to all of SOURCE's.",
        "zh": "只同步这个服务，可重复指定；默认同步 SOURCE 的全部。",
    },
    "cli.help.mcp_sync_overwrite": {
        "en": "Replace same-named servers in the targets instead of skipping them.",
        "zh": "目标里有同名服务时覆盖，而不是跳过。",
    },
    "cli.help.mcp_dry_run": {
        "en": "Show what would change without writing anything.",
        "zh": "只展示会改什么，不写入任何文件。",
    },
    "cli.help.mcp_serve_http": {
        "en": "Run in Streamable HTTP mode (default: stdio, which desktop "
        "tools start as a subprocess).",
        "zh": "以 Streamable HTTP 模式运行 (默认 stdio，桌面工具子进程拉起即用)。",
    },
    "cli.help.mcp_serve_port": {
        "en": "Port for HTTP mode (default: 8525).",
        "zh": "HTTP 模式端口 (默认 8525)。",
    },
    "cli.help.mcp_serve_group": {
        "en": "Filter skills by a config.json group, e.g. --group work; "
        "mounts all of them by default.",
        "zh": "按 config.json 的组过滤技能，如 --group work；默认挂载全部。",
    },
    "cli.help.mcp_serve_allow_write": {
        "en": "Register skill.run / task.run, allowing skill scripts "
        "and tasks to run (read-only by default).",
        "zh": "注册 skill.run / task.run，允许执行技能脚本与任务 (默认只读)。",
    },
    "cli.help.mcp_serve_trust_hooks": {
        "en": "Also register hook.fire (arbitrary command execution, "
        "the most dangerous); implies --allow-write.",
        "zh": "再额外注册 hook.fire (任意命令执行，最高危)；隐含 --allow-write。",
    },
    "cli.desc.mcp_serve": {
        "en": "Serve CodeAgent assets (skills) as an MCP server.\n"
        "\n"
        "Exposes CodeAgent's own skills as MCP tools/resources, so any "
        "MCP-capable client (CodeBuddy / Trae / Cursor / claude / codex) can "
        "consume them. Read-only by default and never touches an API key; "
        "use --allow-write / --trust-hooks to enable the write-side tools.\n"
        "\n"
        "\x08\n"
        "Connect from the client:\n"
        "  stdio:  uv run python -m core.services.mcp_server_service\n"
        "          (or the subprocess command of `ca mcp serve`)\n"
        "  http:   http://127.0.0.1:8525",
        "zh": "把 CodeAgent 的资产 (技能) 作为 MCP 服务暴露出去。\n"
        "\n"
        "把 CodeAgent 自己的 skills 按 MCP 标准暴露成 tools/resources，让任何支持 MCP 的客户端 "
        "(CodeBuddy / Trae / Cursor / claude / codex) 都能直接消费。默认只读，不接触任何 API "
        "密钥；用 --allow-write / --trust-hooks 开启写类工具。\n"
        "\n"
        "\x08\n"
        "在客户端里连接:\n"
        "  stdio:  uv run python -m core.services.mcp_server_service\n"
        "          (或 ca mcp serve 的子进程命令)\n"
        "  http:   http://127.0.0.1:8525",
    },
    "cli.desc.history": {"en": "Session history management.", "zh": "会话历史管理。"},
    "cli.desc.history_list": {
        "en": "List this project's sessions, most recent first.",
        "zh": "列出这个项目的会话，最新的在前。",
    },
    "cli.desc.history_show": {
        "en": "Show full session content.",
        "zh": "展开一条会话的完整内容。",
    },
    "cli.desc.history_convert": {
        "en": "Convert session to another engine format.",
        "zh": "把会话转换成另一个引擎的格式。",
    },
    "cli.help.history_engine": {"en": "Filter by engine", "zh": "只看这个引擎的会话"},
    "cli.help.history_subagents": {
        "en": "Also list subagent runs, which belong to the session that spawned them",
        "zh": "把子任务也列出来 (它们隶属于派生它们的那条会话)",
    },
    "cli.help.history_limit": {
        "en": "How many recent sessions to list (0 lists them all)",
        "zh": "列出最近多少条会话 (0 表示全部)",
    },
    "cli.help.history_yes": {
        "en": "Skip the confirmation prompt",
        "zh": "跳过确认提示",
    },
    "config.seeded": {
        "en": "Created {path} from the bundled template (first launch)",
        "zh": "已根据内置模板创建 {path} (首次启动)",
    },
    "config.load_failed": {
        "en": "[!] Warning: Failed to load config.json: {error}",
        "zh": "[!] 警告: 加载 config.json 失败: {error}",
    },
    "engine.unknown_default": {
        "en": "[!] Unknown default_engine {value!r} in config.json; falling "
        "back to {fallback}.\n"
        "    Known engines: {known}",
        "zh": "[!] config.json 中的 default_engine {value!r} 无法识别，本次回退到 "
        "{fallback}。\n"
        "    可用引擎: {known}",
    },
    "engine.yolo_warning": {
        "en": "[!] YOLO mode is ON: the engine may edit files and run commands "
        "without asking for approval.",
        "zh": "[!] YOLO 模式已开启: 引擎可能不经确认就修改文件、执行命令。",
    },
    "status.title": {"en": "CodeAgent status", "zh": "CodeAgent 状态"},
    "status.section_project": {"en": "Project", "zh": "项目"},
    "status.section_resources": {
        "en": "Resources in group {group}",
        "zh": "分组 {group} 的资源",
    },
    "status.section_engines": {"en": "Engines", "zh": "引擎"},
    "status.label_cwd": {"en": "Directory", "zh": "当前目录"},
    "status.label_group": {"en": "Resource group", "zh": "资源分组"},
    "status.label_projects": {"en": "Registered projects", "zh": "已登记项目"},
    "status.group_unregistered": {
        "en": "{group} (this directory is not registered)",
        "zh": "{group}（当前目录未登记）",
    },
    "status.group_register_hint": {
        "en": "ca project add . --group <group>",
        "zh": "ca project add . --group <组名>",
    },
    "status.projects_count": {"en": "{count}", "zh": "{count} 个"},
    "status.group_missing": {
        "en": "no group {group} in config.json",
        "zh": "config.json 里没有分组 {group}",
    },
    "status.kind_skills": {"en": "skills", "zh": "技能"},
    "status.kind_prompts": {"en": "prompts", "zh": "规范"},
    "status.kind_hooks": {"en": "hooks", "zh": "钩子"},
    "status.kind_plugins": {"en": "plugins", "zh": "插件"},
    "status.resource_count": {"en": "{kind} {count}", "zh": "{kind} {count}"},
    "status.engine_missing": {"en": "not found on PATH", "zh": "未在 PATH 上找到"},
    "ui.open_in_browser": {
        "en": "Open the UI in your browser: {url}",
        "zh": "请在浏览器中打开: {url}",
    },
    "ui.missing_dependency": {
        "en": "[X] Missing dependency for 'ca ui': {module}\n"
        "Install project dependencies first:\n"
        "  uv sync\n"
        "or:\n"
        "  pip install -e .",
        "zh": "[X] 运行 'ca ui' 缺少依赖: {module}\n"
        "请先安装项目依赖:\n"
        "  uv sync\n"
        "或:\n"
        "  pip install -e .",
    },
    "ui.node_modules_installing": {
        "en": "Frontend dependencies (node_modules) not found. Installing ...",
        "zh": "未检测到前端依赖 (node_modules)，正在安装 ...",
    },
    "ui.node_modules_install_failed": {
        "en": "Failed to install frontend dependencies: {error}",
        "zh": "安装前端依赖失败: {error}",
    },
    "ui.vite_starting": {
        "en": "Starting Vite dev server at http://{host}:{port} ...",
        "zh": "正在启动 Vite 开发服务器 http://{host}:{port} ...",
    },
    "ui.vite_failed_fallback": {
        "en": "[!] Failed to start Vite dev server; falling back to built UI.",
        "zh": "[!] Vite 开发服务器启动失败，回退到已构建的界面。",
    },
    "ui.vite_failed_no_dist": {
        "en": "[X] Failed to start Vite dev server, and no built UI was "
        "found.\n"
        "Install frontend deps in web/frontend and retry.",
        "zh": "[X] Vite 开发服务器启动失败，且找不到已构建的界面。\n请先在 web/frontend 安装前端依赖后重试。",
    },
    "ui.vite_detected": {
        "en": "Detected Vite dev server at {url}",
        "zh": "检测到 Vite 开发服务器: {url}",
    },
    "ui.api_starting": {
        "en": "Starting Web UI API at http://127.0.0.1:{port} ...",
        "zh": "正在启动 Web UI 接口服务 http://127.0.0.1:{port} ...",
    },
    "ui.not_built": {
        "en": "[X] The Web UI has not been built yet (expected {index_path}).\n"
        "\n"
        "Build it once with:\n"
        "  cd {frontend_root}\n"
        "  bun install && bun run build      # or: npm install && npm run build\n"
        "\n"
        "Then run `ca ui` again. For live-reloading frontend work, run `ca ui "
        "--dev` instead to have `ca ui` manage a Vite dev server.",
        "zh": "[X] Web UI 尚未构建 (期望文件: {index_path})。\n"
        "\n"
        "只需构建一次:\n"
        "  cd {frontend_root}\n"
        "  bun install && bun run build      # 或: npm install && npm run build\n"
        "\n"
        "然后重新运行 `ca ui`。如果需要前端热更新开发，改用 `ca ui --dev`，让 `ca ui` 托管 Vite 开发服务器。",
    },
    "ui.dist_stale": {
        "en": "[!] The built UI is older than the frontend sources, so this may be a "
        "stale bundle.\n"
        "    Rebuild:      cd {frontend_root} && bun run build\n"
        "    Or live-reload instead:  ca ui --dev",
        "zh": "[!] 已构建的界面早于前端源码，看到的可能是旧版本。\n"
        "    重新构建:  cd {frontend_root} && bun run build\n"
        "    或改用热更新:  ca ui --dev",
    },
    "ui.starting": {
        "en": "Starting Web UI at {url}...",
        "zh": "正在启动 Web UI: {url}...",
    },
    "ui.non_loopback_warning": {
        "en": "⚠️  Bound to {host}, which is reachable from the network. The "
        "UI token is now the only thing protecting shell access on this "
        "machine. Run `ca ui --show-token` to read it, and prefer "
        "putting an authenticating proxy in front of this server.",
        "zh": "⚠️  已绑定到 {host}，该地址可从网络访问。此时 UI token 是保护本机 shell 权限的唯一屏障。可用 "
        "`ca ui --show-token` 查看 token，并建议在本服务前置一层带认证的反向代理。",
    },
    "ui.non_loopback_tunnel_hint": {
        "en": "    If you only need this from another machine of your "
        "own, an SSH tunnel keeps the server on loopback:\n"
        "      ssh -L {port}:127.0.0.1:{port} <user>@<this-host>",
        "zh": "    如果只是想从自己的另一台机器访问，用 SSH 隧道即可让服务继续留在 loopback 上：\n"
        "      ssh -L {port}:127.0.0.1:{port} <user>@<this-host>",
    },
    "ui.token_line": {"en": "UI token: {token}", "zh": "UI token：{token}"},
    "history.index_building": {
        "en": "Building the session index (one-off; later runs are instant)...",
        "zh": "正在建立会话索引（只需一次，之后秒开）...",
    },
    "history.none": {
        "en": "No sessions found for this project.",
        "zh": "当前项目没有找到任何会话。",
    },
    "history.found": {
        "en": "Found {count} session(s) for {path}:\n",
        "zh": "在 {path} 找到 {count} 个会话:\n",
    },
    "history.subagents_hidden": {
        "en": "  ({count} subagent run(s) hidden -- use --include-subagents)\n",
        "zh": "  (已隐藏 {count} 个子任务，加 --include-subagents 查看)\n",
    },
    "history.more": {
        "en": "\n  (showing the {shown} most recent of {count}; -n 0 lists them all)",
        "zh": "\n  (只显示了最近 {shown} 条，共 {count} 条；加 -n 0 全部列出)",
    },
    "history.show_hint": {
        "en": "\n"
        "Show one:      ca history show <engine> <session_id>\n"
        "Continue it elsewhere:  ca switch <engine> [number]",
        "zh": "\n"
        "查看详情:      ca history show <engine> <session_id>\n"
        "换个引擎继续:  ca switch <引擎> [编号]",
    },
    "history.not_found": {
        "en": "[X] Session not found: {engine}/{session_id}",
        "zh": "[X] 未找到会话: {engine}/{session_id}",
    },
    "history.field_engine": {"en": "Engine:  ", "zh": "引擎:    "},
    "history.field_session": {"en": "Session: ", "zh": "会话:    "},
    "history.field_started": {"en": "Started: ", "zh": "开始于:  "},
    "history.field_messages": {"en": "Messages:", "zh": "消息数:  "},
    "history.field_model": {"en": "Model:   ", "zh": "模型:    "},
    "history.unknown_model": {"en": "(unknown)", "zh": "(未知)"},
    "history.no_title": {"en": "(no title)", "zh": "(无标题)"},
    "history.role_user": {"en": "USER", "zh": "用户"},
    "history.role_assistant": {"en": "ASSISTANT", "zh": "助手"},
    "convert.about_to": {
        "en": "About to convert a session (the source session is left untouched):",
        "zh": "即将转换会话 (源会话不会被修改):",
    },
    "convert.line_source": {
        "en": "  Source: {engine}/{session_id}  ({count} msgs)",
        "zh": "  来源: {engine}/{session_id}  (共 {count} 条消息)",
    },
    "convert.line_title": {"en": "  Title:  {title}", "zh": "  标题: {title}"},
    "convert.line_target": {"en": "  Target: {engine}", "zh": "  目标: {engine}"},
    "convert.needs_confirmation": {
        "en": "[X] Refusing to convert without confirmation in a "
        "non-interactive session. Re-run with --yes to skip this "
        "prompt.",
        "zh": "[X] 非交互环境下不会在未确认时执行转换。请加上 --yes 重新运行以跳过确认。",
    },
    "convert.confirm": {"en": "Proceed with conversion?", "zh": "确认执行转换?"},
    "convert.cancelled": {"en": "Cancelled.", "zh": "已取消。"},
    "convert.done": {
        "en": "[OK] Converted {source} -> {target}",
        "zh": "[OK] 已转换 {source} -> {target}",
    },
    "convert.new_id": {
        "en": "   New session ID: {session_id}",
        "zh": "   新会话 ID: {session_id}",
    },
    "convert.resume_claude": {
        "en": "   Resume with: claude -r {session_id}",
        "zh": "   恢复方式: claude -r {session_id}",
    },
    "convert.resume_codex": {
        "en": "   Resume with: codex continue",
        "zh": "   恢复方式: codex continue",
    },
    "convert.resume_codebuddy": {
        "en": "   Resume with: codebuddy --resume {session_id}",
        "zh": "   恢复方式: codebuddy --resume {session_id}",
    },
    "convert.resume_opencode": {
        "en": "   Resume with: opencode (select from history)",
        "zh": "   恢复方式: opencode (从历史记录中选择)",
    },
    "convert.resume_antigravity": {
        "en": "   Resume with: agy --conversation {session_id}",
        "zh": "   恢复方式: agy --conversation {session_id}",
    },
    "convert.failed": {
        "en": "[X] Conversion failed: {error}",
        "zh": "[X] 转换失败: {error}",
    },
    "resume.title": {
        "en": "Recent sessions in {path} ({count} found):",
        "zh": "当前项目的最近会话 ({count} 条，目录: {path}):",
    },
    "resume.more": {
        "en": "  (showing the {shown} most recent of {count}; run `ca history` for the "
        "rest)",
        "zh": "  (只显示最近 {shown} 条，共 {count} 条；其余用 `ca history` 查看)",
    },
    "resume.no_sessions": {
        "en": "[X] No session history found for {path}.\n"
        "Start one first, e.g.:  ca claude",
        "zh": "[X] 在 {path} 没有找到任何历史会话。\n请先启动一个引擎开启会话，例如:  ca claude",
    },
    "resume.select_prompt": {
        "en": "Select a session to resume (↑/↓ to navigate, Enter to resume):",
        "zh": "请选择要恢复的历史会话 (↑/↓ 键选择，Enter 确认恢复):",
    },
    "resume.prompt": {
        "en": "Select session to resume [1-{count}] (Enter for [1], 'q' to quit):",
        "zh": "请选择要恢复的会话 [1-{count}] (直接回车默认 [1]，输入 q 退出):",
    },
    "resume.launching": {
        "en": "Resuming {engine} session: {title}",
        "zh": "正在恢复 {engine} 会话: {title}",
    },
    "resume.invalid_index": {
        "en": "[X] Invalid session number [{index}] -- this project has {count}.",
        "zh": "[X] 无效的会话序号 [{index}] —— 当前项目共有 {count} 条会话。",
    },
    "resume.invalid_choice": {
        "en": "[X] Invalid choice '{input}'. Please enter a number between 1 "
        "and {count}, or 'q' to quit.",
        "zh": "[X] 无效输入 '{input}'。请输入 1 到 {count} 之间的数字，或输入 'q' 退出。",
    },
    "resume.not_found": {
        "en": "[X] No session matching {selector!r} in this project.",
        "zh": "[X] 当前项目没有匹配 {selector!r} 的会话。",
    },
    "resume.no_resume_command": {
        "en": "[X] Cannot build resume command: {error}",
        "zh": "[X] 无法生成恢复命令: {error}",
    },
    "time.just_now": {"en": "just now", "zh": "刚刚"},
    "time.minutes_ago": {"en": "{minutes}m ago", "zh": "{minutes} 分钟前"},
    "time.hours_ago": {"en": "{hours}h ago", "zh": "{hours} 小时前"},
    "time.yesterday": {"en": "yesterday", "zh": "昨天"},
    "time.days_ago": {"en": "{days}d ago", "zh": "{days} 天前"},
    "select.no_sessions": {
        "en": "[X] No sessions found for {path}.\nStart one first, e.g.:  ca claude",
        "zh": "[X] 在 {path} 没有找到任何会话。\n请先开一个,例如:  ca claude",
    },
    "select.index_out_of_range": {
        "en": "[X] No session [{index}] -- this project has {count}. Run "
        "`ca history` to see them.",
        "zh": "[X] 没有第 [{index}] 个会话 —— 这个项目共 {count} 个。运行 `ca history` "
        "查看。",
    },
    "select.not_found": {
        "en": "[X] No session matching {selector!r} in this project.",
        "zh": "[X] 这个项目里没有匹配 {selector!r} 的会话。",
    },
    "switch.candidate_title_with_target": {
        "en": "Candidate source sessions to switch (target: {target}):",
        "zh": "接力候选源会话 (目标: {target}):",
    },
    "switch.candidate_title": {
        "en": "Candidate source sessions to switch:",
        "zh": "接力候选源会话:",
    },
    "switch.default_marker": {"en": "(default)", "zh": "(默认)"},
    "switch.prompt_source": {
        "en": "Confirm source session to switch to {target} [1-{count}] (Enter "
        "for [1], number to change, q to quit):",
        "zh": "请确认要接力给 {target} 的源会话 [1-{count}] (直接回车默认 [1]，输入序号换选，q 退出):",
    },
    "switch.prompt_source_no_target": {
        "en": "Select source session [1-{count}] (Enter for [1], "
        "number to change, q to quit):",
        "zh": "请选择要接力的源会话 [1-{count}] (直接回车默认 [1]，输入序号换选，q 退出):",
    },
    "switch.select_source_with_target": {
        "en": "Select the session to carry over to {target} (↑/↓ to "
        "navigate, Enter to confirm):",
        "zh": "请选择要接力给 {target} 的会话 (↑/↓ 键选择，Enter 确认):",
    },
    "switch.select_source": {
        "en": "Select the session to carry over (↑/↓ to navigate, Enter to confirm):",
        "zh": "请选择要接力的会话 (↑/↓ 键选择，Enter 确认):",
    },
    "switch.select_target": {
        "en": "Select the engine to carry it on in (↑/↓ to navigate, Enter to "
        "confirm):",
        "zh": "请选择要接力到的引擎 (↑/↓ 键选择，Enter 确认):",
    },
    "switch.target_engine_title": {
        "en": "Select target engine to switch to:",
        "zh": "请选择要接力到的目标引擎:",
    },
    "switch.prompt_target": {
        "en": "Target engine [1-{count}] (Enter number or engine name, q to quit):",
        "zh": "目标引擎 [1-{count}] (输入序号或引擎名称，q 退出):",
    },
    "switch.missing_target": {
        "en": "[X] Target engine is required in non-interactive mode. Run `ca "
        "switch <target_engine>` or `ca -s <target_engine>`.",
        "zh": "[X] 非交互模式下必须指定目标引擎。请运行 `ca switch <目标引擎>` 或 `ca -s <目标引擎>`。",
    },
    "switch.unknown_engine": {
        "en": "[X] Unknown engine: {engine}",
        "zh": "[X] 未知引擎: {engine}",
    },
    "switch.known_engines": {
        "en": "    Known engines: {engines}",
        "zh": "    可用引擎: {engines}",
    },
    "switch.converting": {
        "en": "Carrying {source} -> {target}  ({count} msgs)  {title}",
        "zh": "正在从 {source} 切换到 {target}  (共 {count} 条消息)  {title}",
    },
    "switch.already_native": {
        "en": "Already a {engine} session, resuming it as-is:  {title}",
        "zh": "这本来就是 {engine} 的会话,直接继续:  {title}",
    },
    "switch.launching": {
        "en": "Handing it to {engine}...\n",
        "zh": "正在交给 {engine}...\n",
    },
    "switch.no_resume_command": {
        "en": "[X] Cannot build a resume command: {error}",
        "zh": "[X] 无法构造恢复命令: {error}",
    },
    "switch.engine_not_installed": {
        "en": "[!] The session was converted, but the {engine} CLI is not "
        "on PATH, so it could not be launched.",
        "zh": "[!] 会话已经转换好了,但 PATH 上找不到 {engine} 的 CLI,没能拉起来。",
    },
    "switch.resume_manually": {
        "en": "    Resume it with:  {command}",
        "zh": "    继续这个会话:  {command}",
    },
    "ps.none_running": {"en": "No running tasks.", "zh": "没有正在运行的任务。"},
    "ps.none_tracked": {"en": "No tracked task runs.", "zh": "没有已记录的任务运行。"},
    "ps.hint": {
        "en": "\n"
        "Use `ca stop <task id>` to terminate one, or `ca ps --all` to see recent "
        "history.",
        "zh": "\n使用 `ca stop <task id>` 终止某个任务，或 `ca ps --all` 查看历史记录。",
    },
    "stop.not_found": {
        "en": "[X] No such task run: {task_id}",
        "zh": "[X] 没有这个任务运行记录: {task_id}",
    },
    "stop.list_hint": {
        "en": "   Use `ca ps --all` to see known task ids.",
        "zh": "   使用 `ca ps --all` 查看已知的任务 id。",
    },
    "stop.not_running": {
        "en": "[!] Task {task_id} is not running (status: {status}).",
        "zh": "[!] 任务 {task_id} 并未在运行 (状态: {status})。",
    },
    "stop.stopped": {"en": "[OK] Stopped {task_id}", "zh": "[OK] 已停止 {task_id}"},
    "stop.failed": {
        "en": "[X] Failed to stop {task_id}",
        "zh": "[X] 停止 {task_id} 失败",
    },
    "batch.no_projects": {
        "en": "[X] No registered projects{scope} found in project_registry.",
        "zh": "[X] project_registry 中没有{scope}已注册的项目。",
    },
    "batch.scope_group": {"en": " in group '{group}'", "zh": "属于组 '{group}' 的"},
    "batch.no_task": {
        "en": "[X] No such task: {task} (looked in {root})",
        "zh": "[X] 没有这个任务: {task} (查找路径: {root})",
    },
    "batch.plan_header": {
        "en": "{count} project(s) will run '{task}' with {engine}:",
        "zh": "将有 {count} 个项目使用 {engine} 运行 '{task}':",
    },
    "batch.plan_row": {
        "en": "  - {path}  (group: {group})",
        "zh": "  - {path}  (组: {group})",
    },
    "batch.dry_run": {
        "en": "\n(dry run — nothing started)",
        "zh": "\n(演练模式 — 未启动任何任务)",
    },
    "batch.started_row": {
        "en": "  [OK] started {task_id}  ({workspace})",
        "zh": "  [OK] 已启动 {task_id}  ({workspace})",
    },
    "batch.skipped_row": {
        "en": "  [--] skipped, already running  ({workspace})",
        "zh": "  [--] 已跳过，任务正在运行中  ({workspace})",
    },
    "batch.failed_row": {
        "en": "  [X] failed: {reason}  ({workspace})",
        "zh": "  [X] 失败: {reason}  ({workspace})",
    },
    "batch.summary": {
        "en": "\n{started} started, {skipped} skipped, {failed} failed.",
        "zh": "\n已启动 {started} 个，跳过 {skipped} 个，失败 {failed} 个。",
    },
    "batch.track_hint": {
        "en": "Use `ca ps` to track progress, `ca stop <task_id>` to cancel one.",
        "zh": "使用 `ca ps` 跟踪进度，`ca stop <task_id>` 取消某个任务。",
    },
    "project.not_a_directory": {
        "en": "[X] Not a directory: {path}",
        "zh": "[X] 不是一个目录: {path}",
    },
    "project.group_missing": {
        "en": "[!] Group '{group}' doesn't exist yet in config.json's groups — "
        "the project will register, but won't have any "
        "skills/prompts/hooks mounted until the group is created (e.g. "
        "via the Web UI's Config Hub).",
        "zh": "[!] config.json 的 groups 中还没有 '{group}' 这个组 —— "
        "项目仍会注册成功，但在该组创建之前不会挂载任何技能/提示词/钩子 (可通过 Web UI 的 Config Hub 创建)。",
    },
    "project.add_ok": {
        "en": "[OK] Registered {path} -> group '{group}'",
        "zh": "[OK] 已注册 {path} -> 组 '{group}'",
    },
    "project.registry_size": {
        "en": "   project_registry now has {count} entries.",
        "zh": "   project_registry 现有 {count} 条记录。",
    },
    "project.remove_missing": {
        "en": "[!] {path} was not found in project_registry.",
        "zh": "[!] project_registry 中找不到 {path}。",
    },
    "project.removed": {
        "en": "[OK] Removed {path} from project_registry.",
        "zh": "[OK] 已从 project_registry 移除 {path}。",
    },
    "project.none_registered": {
        "en": "No projects registered.",
        "zh": "尚未注册任何项目。",
    },
    "project.list_row": {
        "en": "  {mark}  {path}  group: {group}  {note}",
        "zh": "  {mark}  {path}  组: {group}  {note}",
    },
    "project.missing_marker": {
        "en": "<- directory no longer exists",
        "zh": "← 目录已不存在",
    },
    "project.current_marker": {"en": "<- you are here", "zh": "← 当前目录"},
    "resources.none": {"en": "No {kind} found.", "zh": "没有找到任何{kind}。"},
    "resources.header": {
        "en": "{kind} ({count}) — {label}",
        "zh": "{kind} ({count}) — {label}",
    },
    "resources.label_active": {"en": "active", "zh": "已生效"},
    "resources.label_enabled_in": {
        "en": "enabled in '{group}'",
        "zh": "在 '{group}' 中已启用",
    },
    "cli.cancelled": {"en": "\n\nCancelled", "zh": "\n\n已取消"},
    "cli.specify_engine": {
        "en": "Please specify an engine to launch (e.g. ca claude). Available "
        "engines: {engines}",
        "zh": "请指定要启动的引擎（例如 ca claude）。可用引擎: {engines}",
    },
    "cli.unknown_engine_or_command": {
        "en": "Unknown engine or command: '{name}'. Available engines: "
        "{engines}. Run 'ca --help' for available commands.",
        "zh": "未知的引擎或命令: '{name}'。可用引擎: {engines}。运行 'ca --help' "
        "查看可用命令。",
    },
    "launcher.banner_title": {
        "en": "CodeAgent: Professional AI Engineering Shell",
        "zh": "CodeAgent 统一 AI 编程辅助平台",
    },
    "launcher.project_label": {"en": "Project", "zh": "当前项目"},
    "launcher.latest_session_label": {"en": "Latest", "zh": "最近会话"},
    "launcher.select_action": {"en": "What would you like to do?", "zh": "请选择操作:"},
    "launcher.resume_latest": {
        "en": "🔄 Resume latest ({engine}) · {time} ({title})",
        "zh": "🔄 继续上次会话 ({engine}) · {time} ({title})",
    },
    "launcher.group_sessions": {"en": "Sessions & Engines", "zh": "会话与引擎"},
    "launcher.group_tools": {"en": "Workspaces & Metrics", "zh": "工作台与监控"},
    "launcher.group_manage": {"en": "System & Tools", "zh": "系统与管理"},
    "launcher.engine_ready": {"en": "● Ready", "zh": "● 已就绪"},
    "launcher.engine_missing": {"en": "○ Not Found", "zh": "○ 未安装"},
    "launcher.launch_engine": {
        "en": "🚀 Launch Engine       Codex, Claude, OpenCode, Antigravity, CodeBuddy",
        "zh": "🚀 启动 AI 引擎       Codex / Claude / OpenCode / Antigravity / "
        "CodeBuddy",
    },
    "launcher.browse_sessions": {
        "en": "📜 Browse Sessions     Interactive session list across all "
        "engines (ca -r)",
        "zh": "📜 浏览历史会话       跨引擎选择并恢复历史会话 (ca -r)",
    },
    "launcher.switch_session": {
        "en": "⚡ Switch Engine       Relay current conversation to another "
        "engine (ca -s)",
        "zh": "⚡ 跨引擎会话接力     将当前会话一键转至另一引擎 (ca -s)",
    },
    "launcher.web_ui": {
        "en": "🌐 Web Dashboard       Open full-featured browser GUI (ca ui)",
        "zh": "🌐 启动 Web 控制台    打开全功能浏览器图形界面 (ca ui)",
    },
    "launcher.status": {
        "en": "📊 Project Status      Inspect resource group & engines (ca status)",
        "zh": "📊 查看系统状态       查看项目分组与引擎状态 (ca status)",
    },
    "launcher.doctor": {
        "en": "🩺 Health Check & Auto-Repair (ca doctor)",
        "zh": "🩺 环境健康检查与修复 (ca doctor)",
    },
    "launcher.help": {
        "en": "❓ View Full Command Help (--help)",
        "zh": "❓ 查看完整命令帮助 (--help)",
    },
    "launcher.more": {
        "en": "📋 More Actions...     Sync standards / Install MCP / Health check / Help",
        "zh": "📋 更多操作...        规范同步 / MCP 安装 / 健康检查 / 帮助",
    },
    "launcher.back": {"en": "↩️  Back", "zh": "↩️  返回上一级"},
    "launcher.exit": {"en": "🚪 Exit", "zh": "🚪 退出"},
    "launcher.select_engine": {
        "en": "Select engine to launch:",
        "zh": "请选择要启动的引擎:",
    },
}
