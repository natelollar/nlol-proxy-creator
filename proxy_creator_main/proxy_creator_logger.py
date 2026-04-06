import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


class ProxyCreatorLogger:
    """Custom logging class for Maya. Writes to both console and log file."""

    def __init__(self) -> None:
        """Logger for proxy creator. Writes to a rotating log file."""
        self.root_folderpath = Path(__file__).parents[1]
        self.log_filepath = self.root_folderpath / "logger.log"

        self.logger = logging.getLogger("proxy_creator_log")

        if not self.logger.handlers:
            file_formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            )
            file_handler = RotatingFileHandler(
                self.log_filepath,
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
            )
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)

            console_handler = logging.StreamHandler()
            console_handler.setFormatter(file_formatter)
            self.logger.addHandler(console_handler)

            self.set_log_level()

    def set_log_level(self):
        """Set the logging level based on the debug_mode variable."""
        debug_mode = True
        if debug_mode:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)


_logger_instance = None


def get_logger() -> logging.Logger:
    """Returns:
    Logger instance.
    """
    global _logger_instance
    if _logger_instance is None:
        maya_logger = ProxyCreatorLogger()
        _logger_instance = maya_logger.logger
    return _logger_instance
