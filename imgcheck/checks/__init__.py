from .metadata import check_metadata
from .c2pa_check import check_c2pa
from .ela import check_ela
from .noise import check_noise
from .copymove import check_copymove
from .ai_api import check_ai_api

ALL_CHECKS = [
    check_metadata,
    check_c2pa,
    check_ela,
    check_noise,
    check_copymove,
    check_ai_api,
]
