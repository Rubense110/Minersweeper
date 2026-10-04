"""Default search budget and reference grid for the four quality objectives."""

DEFAULT_POPULATION_SIZE = 36
DEFAULT_N_PARTITIONS = 4
# Initial population plus 50 complete offspring generations.
DEFAULT_MAX_EVALUATIONS = DEFAULT_POPULATION_SIZE * 51


def normalize_population_size(value: int | None) -> int | None:
    """SBX uses pairs: an odd request means the next even population."""
    if value is None:
        return None
    try:
        size = int(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("population_size must be a positive integer or null") from error
    if isinstance(value, bool) or size < 1 or (not isinstance(value, str) and size != value):
        raise ValueError("population_size must be a positive integer or null")
    return size + size % 2
