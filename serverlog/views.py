# Create your views here.
import logging
logger = logging.getLogger(__name__)
 
def debug_msg():
    logger.debug("this is a debug message!")
 
def error_msg():
    logger.error("this is an error message!!")

