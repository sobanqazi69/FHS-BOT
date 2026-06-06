import logging
import subprocess

logger = logging.getLogger(__name__)


def open_xbox():
    subprocess.Popen(["explorer.exe", "xbox:"])
    logger.info("Xbox app launched.")
