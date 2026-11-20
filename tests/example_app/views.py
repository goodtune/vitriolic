from django.urls import reverse
from django.views.generic import CreateView, DetailView, TemplateView

from .forms import AcceptanceForm
from .models import Acceptance


class IndexView(TemplateView):
    template_name = "base.html"


class SignView(CreateView):
    """Sign an acceptance: the page a ``SignatureField`` is seen on."""

    form_class = AcceptanceForm
    template_name = "example_app/signature/sign.html"

    def get_success_url(self):
        return reverse("signed", args=[self.object.pk])


class SignedView(DetailView):
    model = Acceptance
    template_name = "example_app/signature/signed.html"


index = IndexView.as_view()
sign = SignView.as_view()
signed = SignedView.as_view()
