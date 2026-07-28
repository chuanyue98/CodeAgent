import logging

import core.logging_config as logging_config


def _reset():
    logging_config._configured = False
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)


def test_configure_root_logging_defaults_to_info(monkeypatch):
    _reset()
    monkeypatch.delenv("CA_DEBUG", raising=False)
    logging_config.configure_root_logging()
    assert logging.getLogger().level == logging.INFO
    _reset()


def test_configure_root_logging_respects_ca_debug(monkeypatch):
    _reset()
    monkeypatch.setenv("CA_DEBUG", "1")
    logging_config.configure_root_logging()
    assert logging.getLogger().level == logging.DEBUG
    _reset()


def test_configure_root_logging_explicit_level_overrides_env(monkeypatch):
    _reset()
    monkeypatch.setenv("CA_DEBUG", "1")
    logging_config.configure_root_logging(level=logging.WARNING)
    assert logging.getLogger().level == logging.WARNING
    _reset()


def test_configure_root_logging_only_adds_handler_once(monkeypatch):
    _reset()
    monkeypatch.delenv("CA_DEBUG", raising=False)
    logging_config.configure_root_logging()
    logging_config.configure_root_logging()
    assert len(logging.getLogger().handlers) == 1
    _reset()


def test_get_logger_returns_named_logger():
    _reset()
    logger = logging_config.get_logger("codeagent.test.module")
    assert logger.name == "codeagent.test.module"
    _reset()


def test_get_logger_lazily_configures_root_when_unconfigured(monkeypatch):
    _reset()
    monkeypatch.delenv("CA_DEBUG", raising=False)
    logging_config.get_logger(__name__)
    assert logging_config._configured is True
    assert len(logging.getLogger().handlers) == 1
    _reset()
