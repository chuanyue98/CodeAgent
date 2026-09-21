"""跨线程唤醒运行日志的流式订阅者。

后台运行（``TaskRunner.run_task``）的 stdout 由一条普通线程泵出
（见 ``TaskRunner._pump_stdout``），而消费日志的 SSE 端点跑在事件循环上。
没有这个信号时，端点无从得知「刚刚又写进来一段」，只能靠定时重新 stat 日志
文件 —— 于是每次推送的延迟都被那个间隔兜住。

订阅按 run 粒度、按需建立：一个没人看的运行，除了一次加锁不做任何事。
"""

from __future__ import annotations

import asyncio
import threading


class LogSubscription:
    """单个流式客户端对某个运行输出的等待句柄。"""

    __slots__ = ("_broker", "_run_id", "_token", "_loop", "_event")

    def __init__(
        self,
        broker: LogBroker,
        run_id: str,
        token: int,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._broker = broker
        self._run_id = run_id
        self._token = token
        self._loop = loop
        self._event = asyncio.Event()

    def arm(self) -> None:
        """复位唤醒标志，使下一次 ``wait`` 只对之后写入的数据生效。

        消费者应先在文件上做一轮读取、再 ``arm``+``wait``；顺序反过来的话，
        在「复位」与「等待」之间落盘的数据会丢掉那次唤醒。
        """
        self._event.clear()

    async def wait(self, timeout: float) -> bool:
        """等待泵写入，或等到 *timeout* 秒超时。

        Returns:
            bool: 收到唤醒为 True，超时为 False。
        """
        try:
            await asyncio.wait_for(self._event.wait(), timeout)
        except TimeoutError:
            return False
        return True

    def release(self) -> None:
        """取消订阅，幂等。"""
        self._broker._release(self._run_id, self._token)

    def _notify(self) -> None:
        """从任意线程把事件循环叫醒；循环已关闭时静默放弃。"""
        try:
            self._loop.call_soon_threadsafe(self._event.set)
        except RuntimeError:
            # 解释器正在关停（或循环已关）：已经没有消费者要通知了。
            return


class LogBroker:
    """把一个运行的 stdout 写入事件广播给任意数量的等待者。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._live: set[str] = set()
        self._waiters: dict[str, dict[int, LogSubscription]] = {}
        self._next_token = 0

    def register(self, run_id: str) -> None:
        """声明某个运行的输出正由本进程泵出。

        在 SSE 端点里这区分了「本进程新起的运行」（可以等唤醒）与「重启前留下的
        旧运行」（没有泵线程，只能继续轮询文件）。
        """
        with self._lock:
            self._live.add(run_id)

    def is_live(self, run_id: str) -> bool:
        """该运行的输出是否正由本进程泵出。"""
        with self._lock:
            return run_id in self._live

    def notify(self, run_id: str) -> None:
        """泵线程刚写入一段输出，唤醒所有等待者。"""
        for subscription in self._watchers(run_id):
            subscription._notify()

    def finish(self, run_id: str) -> None:
        """泵线程已到 EOF：唤醒等待者，不再自称实时。"""
        with self._lock:
            self._live.discard(run_id)
        for subscription in self._watchers(run_id):
            subscription._notify()

    def subscribe(self, run_id: str) -> LogSubscription:
        """创建一个订阅；调用方负责在结束时 ``release()``。"""
        loop = asyncio.get_running_loop()
        with self._lock:
            self._next_token += 1
            token = self._next_token
            subscription = LogSubscription(self, run_id, token, loop)
            self._waiters.setdefault(run_id, {})[token] = subscription
        return subscription

    def _watchers(self, run_id: str) -> list[LogSubscription]:
        with self._lock:
            return list(self._waiters.get(run_id, {}).values())

    def _release(self, run_id: str, token: int) -> None:
        with self._lock:
            waiters = self._waiters.get(run_id)
            if waiters is None:
                return
            waiters.pop(token, None)
            if not waiters:
                self._waiters.pop(run_id, None)
