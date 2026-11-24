# Signature field

`touchtechnology.common` has a field for a person's signature, as their acceptance of what a form says.
The person signs in a box with a mouse, a finger or a stylus.
The drawing is done by [Signature Pad](https://github.com/szimek/signature_pad) (MIT licence), which the app ships; nothing is loaded from another site.

## Use it

On a model:

```python
from django.db import models

from touchtechnology.common.db.models import SignatureField


class Acceptance(models.Model):
    name = models.CharField(max_length=100)
    signature = SignatureField()
```

A `ModelForm` of that model gets the signature box.
In a plain form, use the form field:

```python
from django import forms

from touchtechnology.common.forms.fields import SignatureField


class AcceptanceForm(forms.Form):
    signature = SignatureField()
```

The page must load the form's media, which is the script and the style sheet of the box:

```html
<head>
	{{ form.media }}
</head>
```

## What is stored

The value is a PNG image as a data URL, kept in a text column.
A template shows it as it is:

```html
<img src="{{ acceptance.signature }}" alt="The signature of {{ acceptance.name }}">
```

The image has a white background, so it reads the same on any page.
Its size in pixels follows the screen it was signed on.

## What the field checks

- The field is required unless it is given `required=False` (or the model field `blank=True`).
  The box sends nothing until something is drawn, and nothing again after Clear, so an empty box is refused with "Please sign in the box."
- The value must be a whole PNG file.
  Anything else is refused, so that the value is safe to store and to show again.
- The image must be no larger than `max_size` bytes, 512 KB unless you give another: `SignatureField(max_size=1024 * 1024)`.

The field does not judge the drawing.
A single dot is a signature as far as it can tell.

## Without JavaScript

The box needs JavaScript.
With it turned off, the page says so, and a required signature cannot be given.

## Update the library

`touchtechnology/common/static/touchtechnology/common/update-signature-pad.sh` fetches a release from npm and replaces the file.
Give it a version, or nothing for the latest, then put the new version number in the script's comment.

## Tests

`touchtechnology/common/tests/test_signature_field.py` tests what the server does with what it is sent.
`tests/e2e/test_signature_field.py` signs the acceptance form of `example_app` in a browser, with a mouse and with a finger, and takes screenshots.
