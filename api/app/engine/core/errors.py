class EmissionError(Exception):
    """Base class: the service stores this message on the record (NFR-2.10)."""


class UnknownUnitError(EmissionError):
    pass


class MissingFactorError(EmissionError):
    pass