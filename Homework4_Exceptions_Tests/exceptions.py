class CarbonLensException(Exception):
    """Base exception class for the entire application."""
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

# 1. S1 (Data & Identity) Error
class S1_DataValidationError(CarbonLensException):
    pass

# 2. S2 (Emission Engine) Error
class S2_EmissionCalculationError(CarbonLensException):
    pass

# 3. S3 (Analytics) Error
class S3_AnalyticsReportError(CarbonLensException):
    pass

# 4. S4 (AI Coach) Error
class S4_AICoachError(CarbonLensException):
    pass