"""
Logger Configuration
Setup Python built-in logging for application logging
"""
import logging

# Create logger
logger = logging.getLogger("server")
logger.setLevel(logging.DEBUG)

# Console Handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)

# Formatter - [Server] : message
formatter = logging.Formatter('[Server] : %(message)s')
console_handler.setFormatter(formatter)

# Add handler
logger.addHandler(console_handler)

__all__ = ["logger"]
