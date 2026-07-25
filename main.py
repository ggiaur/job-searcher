import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("job-searcher")

from agents.job_search_agent import JobSearchAgent

def main():
    logger.info("Initializing Job Searcher application...")
    agent = JobSearchAgent()
    metrics = agent.run()
    logger.info(f"Execution finished successfully: {metrics}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
