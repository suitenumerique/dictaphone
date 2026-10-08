"""Command line entry point."""

import argparse
import logging

from audio_extractor.sentry import init_sentry
from audio_extractor.settings import Settings
from audio_extractor.worker import run


def main() -> None:
    """Poll for one task and exit after it has been handled."""
    parser = argparse.ArgumentParser(description="Pull and process audio tasks")
    parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    settings = Settings()
    init_sentry(settings)
    run(settings)


if __name__ == "__main__":
    main()
