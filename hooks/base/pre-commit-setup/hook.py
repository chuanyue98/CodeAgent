import subprocess
from pathlib import Path


def main():
    config_file = Path(".pre-commit-config.yaml")
    git_dir = Path(".git")
    hook_file = git_dir / "hooks" / "pre-commit"

    # Only run if it's a git repo and has a pre-commit config
    if config_file.exists() and git_dir.exists():
        if not hook_file.exists():
            print(
                "🔍 [CA Hook] .pre-commit-config.yaml found but hooks not installed. Installing..."
            )
            try:
                # Use 'pre-commit' command directly, assuming it's in PATH
                result = subprocess.run(
                    ["pre-commit", "install"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode == 0:
                    print("✅ [CA Hook] pre-commit hooks installed successfully.")
                else:
                    print(
                        f"⚠️ [CA Hook] pre-commit install failed: {result.stderr.strip()}"
                    )
            except FileNotFoundError:
                print(
                    "❌ [CA Hook] 'pre-commit' command not found. Please install it with: pip install pre-commit"
                )
        else:
            # Already installed, stay silent or debug print
            pass


if __name__ == "__main__":
    main()
