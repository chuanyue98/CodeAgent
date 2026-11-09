"""结束一个进程及它拉起的全部子孙进程。

启动器（``engines/start_*.py``）自己再用 ``subprocess.run`` 拉起引擎 CLI，
引擎又会拉起 node、shell 等。只杀启动器的话，引擎成了孤儿接着跑、接着改
文件；它还握着我们的 stdout 管道，``communicate`` 会一直等到它自己退出。
所以超时要杀整棵树：先在父进程还活着时把子孙列全（父进程一死，子孙就被
系统收养，再也按父子关系找不到），再一起杀掉。
"""

from __future__ import annotations

import psutil

from core.logging_config import get_logger

logger = get_logger(__name__)

_WAIT_SECONDS = 5.0


def kill_process_tree(pid: int) -> None:
    """杀掉 *pid* 及其全部子孙，等它们退出。进程已经不在了就什么都不做。"""
    try:
        root = psutil.Process(pid)
        procs = [*root.children(recursive=True), root]
    except psutil.NoSuchProcess:
        return
    except psutil.Error as exc:
        logger.warning("列出进程 %s 的子进程失败: %s", pid, exc)
        procs = []
        try:
            procs = [psutil.Process(pid)]
        except psutil.Error:
            return
    for proc in procs:
        try:
            proc.kill()
        except psutil.NoSuchProcess:
            pass
        except psutil.Error as exc:
            logger.warning("结束进程 %s 失败: %s", proc.pid, exc)
    _gone, alive = psutil.wait_procs(procs, timeout=_WAIT_SECONDS)
    for proc in alive:
        logger.warning("进程 %s 在 %.0f 秒内没有退出", proc.pid, _WAIT_SECONDS)
