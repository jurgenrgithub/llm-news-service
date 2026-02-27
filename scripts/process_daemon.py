#!/usr/bin/env python3
"""Background processing daemon for article pipeline.

Runs triage and deep analysis on a schedule:
- Triage: every 5 minutes
- Deep Analysis: every 10 minutes
- Cleanup: every hour
"""

import sys
import time
import logging
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import schedule

from core.article_processor import ArticleProcessor
from core.claude_client import ClaudeClient

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_triage():
    """Run triage batch on pending articles."""
    try:
        processor = ArticleProcessor()
        count = processor.run_triage_batch(50)
        if count > 0:
            logger.info(f"Triage: processed {count} articles")
    except Exception as e:
        logger.error(f"Triage error: {e}")


def run_analysis():
    """Run deep LLM analysis on flagged entities."""
    try:
        processor = ArticleProcessor(ClaudeClient())
        count = processor.run_analysis_batch(20)
        if count > 0:
            logger.info(f"Analysis: processed {count} entities")
    except Exception as e:
        logger.error(f"Analysis error: {e}")


def run_cleanup():
    """Clean up expired articles."""
    try:
        processor = ArticleProcessor()
        count = processor.cleanup_expired()
        if count > 0:
            logger.info(f"Cleanup: removed {count} expired articles")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")


def main():
    """Main daemon loop."""
    logger.info("Article processing daemon starting...")
    logger.info("Schedule:")
    logger.info("  - Triage: every 5 minutes")
    logger.info("  - Analysis: every 10 minutes")
    logger.info("  - Cleanup: every hour")

    # Schedule jobs
    schedule.every(5).minutes.do(run_triage)
    schedule.every(10).minutes.do(run_analysis)
    schedule.every(1).hours.do(run_cleanup)

    # Run initial batch on startup
    logger.info("Running initial triage...")
    run_triage()

    # Main loop
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
