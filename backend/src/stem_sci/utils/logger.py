"""Structured logging entry point for framework components."""

import logging


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"stem_sci.{name}")
