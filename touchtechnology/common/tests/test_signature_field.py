"""
``SignatureField``: a person's drawn signature, kept as a PNG data URL.

The drawing itself is the browser's work (Signature Pad, see
``tests/e2e/test_signature_field.py``). These tests are of what the server
does with what it is sent.
"""

import base64
import io

from django import forms
from django.core.exceptions import ValidationError
from PIL import Image
from test_plus import TestCase

from touchtechnology.common.db import models as db
from touchtechnology.common.forms.fields import SignatureField
from touchtechnology.common.forms.widgets import SignatureWidget


def data_url(format="PNG", size=(300, 100), mime="image/png"):
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format=format)
    return f"data:{mime};base64,{base64.b64encode(buffer.getvalue()).decode()}"


class AcceptanceForm(forms.Form):
    signature = SignatureField()


class SignatureFormFieldTests(TestCase):
    def assertRefused(self, value, message, **kwargs):
        with self.assertRaisesMessage(ValidationError, message):
            SignatureField(**kwargs).clean(value)

    def test_png_data_url_is_kept_as_sent(self):
        signature = data_url()
        self.assertEqual(SignatureField().clean(signature), signature)

    def test_signature_is_required_unless_told_otherwise(self):
        self.assertRefused("", "Please sign in the box.")
        self.assertEqual(SignatureField(required=False).clean(""), "")

    def test_text_that_is_no_image_is_refused(self):
        for value in ("Gary Reynolds", "data:image/png;base64,not-base64!"):
            with self.subTest(value):
                self.assertRefused(value, "This is not a signature.")

    def test_image_that_is_no_png_is_refused(self):
        cases = {
            "a JPEG that says it is one": data_url("JPEG", mime="image/jpeg"),
            "a JPEG that says it is a PNG": data_url("JPEG"),
            "a PNG cut short": data_url()[:80],
            "a PNG with something after it": data_url()[:-4] + "AAAA" * 4,
        }
        for name, value in cases.items():
            with self.subTest(name):
                self.assertRefused(value, "This is not a signature.")

    def test_signature_over_the_size_limit_is_refused(self):
        signature = data_url()
        self.assertRefused(
            signature,
            "This signature is too large to keep. Clear it and sign again.",
            max_size=100,
        )
        self.assertEqual(SignatureField(max_size=10_000).clean(signature), signature)


class SignatureWidgetTests(TestCase):
    def test_widget_is_a_canvas_over_a_hidden_input(self):
        self.assertHTMLEqual(
            SignatureWidget().render("signature", None, attrs={"id": "id_signature"}),
            """
            <div class="signature-field" data-signature-field>
                <canvas class="signature-field-canvas" width="600" height="200"
                    role="img" aria-label="Signature"></canvas>
                <input type="hidden" name="signature" id="id_signature">
                <p class="signature-field-actions">
                    <button type="button" class="signature-field-clear"
                        data-signature-clear>Clear</button>
                    <span class="signature-field-hint">Sign in the box with a
                        mouse, a finger or a stylus.</span>
                </p>
                <noscript><p class="signature-field-hint">Signing needs
                    JavaScript, which is turned off in this browser.</p></noscript>
            </div>
            """,
        )

    def test_widget_carries_the_signature_it_was_given(self):
        signature = data_url()
        html = SignatureWidget().render("signature", signature, attrs={"id": "i"})
        self.assertInHTML(
            f'<input type="hidden" name="signature" id="i" value="{signature}">', html
        )

    def test_widget_brings_signature_pad_and_its_own_script(self):
        media = SignatureWidget().media
        self.assertEqual(
            (media._js, media._css),
            (
                [
                    "touchtechnology/common/js/signature_pad.umd.min.js",
                    "touchtechnology/common/js/signature-field.js",
                ],
                {"all": ["touchtechnology/common/css/signature-field.css"]},
            ),
        )

    def test_widget_is_shown_with_its_label_and_is_not_required_by_the_browser(self):
        # A hidden input would lose its label and row; and ``required`` on one
        # does nothing, so the server is what asks for the signature.
        field = AcceptanceForm()["signature"]
        self.assertEqual(
            (field.is_hidden, field.field.widget.use_required_attribute(None)),
            (False, False),
        )

    def test_form_says_what_is_wrong_beside_the_field(self):
        form = AcceptanceForm({"signature": ""})
        self.assertEqual(form.errors, {"signature": ["Please sign in the box."]})


class SignatureModelFieldTests(TestCase):
    def test_model_field_is_text_with_the_signature_form_field(self):
        field = db.SignatureField()
        formfield = field.formfield()
        self.assertEqual(
            (field.get_internal_type(), type(formfield), type(formfield.widget)),
            ("TextField", SignatureField, SignatureWidget),
        )

    def test_model_field_left_blank_makes_the_form_field_optional(self):
        self.assertIs(db.SignatureField(blank=True).formfield().required, False)
