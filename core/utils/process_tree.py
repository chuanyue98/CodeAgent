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


def _is_executing(proc: psutil.Process) -> bool:
    try:
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    except psutil.Error:
        try:
            return proc.is_running()
        except psutil.Error:
            return False


def kill_process_tree(pid: int) -> None:
    """杀掉 *pid* 及其全部子孙，等它们退出。进程已经不在了就什么都不做。"""
    try:
        root = psutil.Process(pid)
        procs = [root, *root.children(recursive=True)]
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


def process_created_at(pid: int) -> float | None:
    """读取身份时间；无权限或已退出时不猜测。"""
    try:
        return psutil.Process(pid).create_time()
    except (psutil.Error, TypeError, ValueError):
        return None


def terminate_process_tree(pid: int, created_at: float | None) -> bool:
    """核对身份后先终止、再强杀；不能确认全部退出就返回 False。"""
    try:
        root = psutil.Process(pid)
        if created_at is None or abs(root.create_time() - created_at) > 0.5:
            logger.warning("拒绝终止无法核对身份的进程 %s", pid)
            return False
        procs = [root, *root.children(recursive=True)]
    except psutil.NoSuchProcess:
        return True
    except psutil.Error:
        logger.warning("无法枚举进程树 %s", pid, exc_info=True)
        return False
    for proc in procs:
        try:
            proc.terminate()
        except psutil.NoSuchProcess:
            pass
        except psutil.Error:
            logger.warning("请求进程 %s 退出失败，将尝试强制终止", proc.pid)
    _, alive = psutil.wait_procs(procs, timeout=2)
    for proc in alive:
        try:
            proc.kill()
        except psutil.NoSuchProcess:
            pass
        except psutil.Error:
            logger.warning("强制终止进程 %s 失败", proc.pid)
    _, alive = psutil.wait_procs(alive, timeout=_WAIT_SECONDS)
    # POSIX 僵尸已不再执行代码，退出状态由其父进程回收。
    return not any(_is_executing(p) for p in alive)
