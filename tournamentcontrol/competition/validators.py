from django.core import validators
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

validate_hashtag = validators.RegexValidator(
    r"^(?:#)(\w+)$",
    _("Enter a valid value. Make sure you include the # symbol."),
)


def validate_logo_aspect_ratio(image, tolerance=0.1):
    """
    Validate that an image has a square aspect ratio (1:1).
    
    This validator is optional and will only run if PIL/Pillow is available.
    If PIL is not available, validation is skipped gracefully.
    
    Args:
        image: Django FieldFile, InMemoryUploadedFile, or file-like object
        tolerance: Acceptable deviation from square (default 0.1 = 10%)
    
    Raises:
        ValidationError: If aspect ratio is not square within tolerance
    """
    try:
        from PIL import Image as PILImage
    except ImportError:
        # PIL/Pillow not available, skip validation
        return
    
    try:
        img = PILImage.open(image)
        width, height = img.size
        
        # Avoid division by zero
        if height == 0:
            raise ValidationError(
                _("Invalid image dimensions."),
                code="invalid_dimensions"
            )
        
        aspect_ratio = width / height
        
        # Check if aspect ratio is close to 1:1 (square)
        # Allow some tolerance for rounding
        if not (1 - tolerance <= aspect_ratio <= 1 + tolerance):
            raise ValidationError(
                _("Logo must be square (1:1 aspect ratio). Current ratio is %(ratio)s:1."),
                code="invalid_aspect_ratio",
                params={"ratio": f"{aspect_ratio:.2f}"}
            )
    except (IOError, OSError):
        # If we can't open the image, let Django's ImageField validation handle it
        # Return silently to avoid duplicate validation errors
        return
