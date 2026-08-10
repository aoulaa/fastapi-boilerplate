class EskizError(Exception):
    """Eskiz endpoint returned a non-2xx response. The endpoint was reached — treat as billable."""


class EskizUnreachable(Exception):
    """Could not reach Eskiz (network / timeout / our-side failure). Retryable, do not bill."""
