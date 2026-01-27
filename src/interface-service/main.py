#!/usr/bin/env python3
"""Main entry point for SentryHub interface service."""

import logging
from sentry_hub_interface import SentryHubInterface

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point."""
    interface = SentryHubInterface()
    interface.run()


if __name__ == "__main__":
    main()
