import numpy as np
import sounddevice as sd
import threading
import time
from collections import defaultdict, deque
import queue
import atexit
import logging
import soundfile as sf
import os
import gc
import warnings
from typing import Union, Optional, Callable, Dict, Set, Tuple, Any, List
import numpy.typing as npt

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("AudioEngine")

# Only ignore specific RuntimeWarning
warnings.filterwarnings(
    "ignore", category=RuntimeWarning, message="divide by zero encountered in .*"
)
