"""
The Workbook interface's own pieces: how a field's control is drawn, where a
page sits (its trail), the home page's jobs, the set-up checklist, and Save
and add another.
"""

from django import forms
from django.template import Context, Template
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse_lazy
from test_plus import TestCase

from touchtechnology.admin.setup import Setup, Step
from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.common.forms.mixins import BootstrapFormControlMixin
from touchtechnology.common.forms.widgets import HTMLWidget, LocationWidget
from touchtechnology.common.tests import factories
from touchtechnology.content.models import Redirect
from touchtechnology.news.tests.factories import ArticleFactory, TranslationFactory

ICON = (
    '<svg class="wb-icon" aria-hidden="true" focusable="false">'
    '<use href="/static/touchtechnology/admin/workbook/icons.svg#%s"></use></svg>'
)


class ChoiceForm(BootstrapFormControlMixin, forms.Form):
    title = forms.CharField(label="Title")
    when = forms.DateField(label="When", widget=forms.DateInput)
    starts = forms.TimeField(label="Starts", widget=forms.TimeInput)
    few = forms.ChoiceField(choices=[(n, "Choice %d" % n) for n in range(3)])
    many = forms.ChoiceField(choices=[(n, "Choice %d" % n) for n in range(12)])
    several = forms.MultipleChoiceField(choices=[("a", "A"), ("b", "B")])
    where = forms.CharField(widget=LocationWidget(height=200, zoom=12))


def render(source, **context):
    return Template("{% load admin_workbook %}" + source).render(Context(context))


@per_shell(shells=("workbook",))
class ControlTests(TestCase):
    """The admin draws each control itself, whatever form it comes from."""

    def test_input_drops_the_old_class_and_a_placeholder_that_repeats_the_label(self):
        self.assertHTMLEqual(
            render("{{ form.title|control }}", form=ChoiceForm()),
            '<input type="text" name="title" class="wb-input" required id="id_title">',
        )

    def test_dates_and_times_use_the_browser_pickers(self):
        form = ChoiceForm(initial={"when": "2026-10-20", "starts": "18:00"})
        self.assertHTMLEqual(
            render("{{ form.when|control }}", form=form),
            '<input type="date" name="when" value="2026-10-20" class="wb-input" '
            'required id="id_when">',
        )
        self.assertHTMLEqual(
            render("{{ form.starts|control }}", form=form),
            '<input type="time" name="starts" value="18:00" class="wb-input" '
            'required id="id_starts">',
        )

    def test_a_short_select_stays_a_select(self):
        self.assertHTMLEqual(
            render("{{ form.few|control }}", form=ChoiceForm()),
            '<select name="few" class="wb-select" id="id_few">'
            '<option value="0">Choice 0</option><option value="1">Choice 1</option>'
            '<option value="2">Choice 2</option></select>',
        )

    def test_a_long_or_multiple_choice_opens_a_dialog(self):
        options = "".join(
            '<option value="%d">Choice %d</option>' % (n, n) for n in range(12)
        )
        self.assertHTMLEqual(
            render("{{ form.many|control }}", form=ChoiceForm()),
            '<select name="many" class="wb-select" data-picker="dialog" id="id_many">'
            "%s</select>" % options,
        )
        self.assertHTMLEqual(
            render("{{ form.several|control }}", form=ChoiceForm()),
            '<select name="several" class="wb-select" data-picker="dialog" '
            'required id="id_several" multiple>'
            '<option value="a">A</option><option value="b">B</option></select>',
        )

    def test_an_error_is_tied_to_its_control(self):
        form = ChoiceForm(data={})
        self.assertHTMLEqual(
            render("{{ form.title|control }}", form=form),
            '<input type="text" name="title" class="wb-input" aria-invalid="true" '
            'aria-describedby="id_title_error" required id="id_title">',
        )

    def test_the_location_widget_is_drawn_and_served_by_the_admin(self):
        form = ChoiceForm()
        drawn = render("{{ form.where|control }}", form=form)
        self.assertInHTML(
            '<button type="button" class="wb-button wb-button-small '
            'location-widget-toggle" aria-pressed="false" hidden>Edit</button>',
            drawn,
        )
        media = str(render("{{ form.media|admin_media }}", form=form))
        self.assertIn("/static/touchtechnology/admin/vendor/leaflet/leaflet.js", media)
        self.assertNotIn("unpkg.com", media)


class CopyForm(BootstrapFormControlMixin, forms.Form):
    copy = forms.CharField(label="Copy", widget=HTMLWidget)


@per_shell(shells=("workbook",))
class RichTextTests(TestCase):
    """The rich-text editor finds its field by the class of the field's box."""

    def test_the_field_box_names_the_widget(self):
        html = Template("{% load common %}{% field form.copy %}").render(
            Context(
                {
                    "form": CopyForm(),
                    "field_template": "touchtechnology/admin/workbook/templatetags/field.html",
                }
            )
        )
        self.assertTrue(
            html.lstrip().startswith(
                '<div class="wb-field wb-field-textarea html_widget">'
            ),
            html[:200],
        )

    def test_the_article_page_carries_the_editor(self):
        article = ArticleFactory.create()
        superuser = factories.UserFactory.create(is_staff=True, is_superuser=True)
        with self.login(superuser):
            self.get_check_200("admin:news:article:edit", article.pk)
        self.assertResponseContains(
            '<script src="/static/touchtechnology/common/js/html-editor.js"></script>',
        )
        self.assertIn(
            '<div class="wb-field wb-field-textarea html_widget">',
            self.last_response.content.decode(),
        )


@per_shell(shells=("workbook",))
class FilterTests(TestCase):
    def test_label_text_drops_the_colon_django_adds(self):
        self.assertEqual(
            render("{{ caption|label_text }}", caption='<label for="x">Title:</label>'),
            '<label for="x">Title</label>',
        )

    def test_resolved_is_empty_for_a_link_with_no_page(self):
        self.assertEqual(
            render("[{{ url|resolved }}]", url=reverse_lazy("admin:nowhere:add")),
            "[]",
        )
        self.assertEqual(
            render("[{{ url|resolved }}]", url=reverse_lazy("admin:index")),
            "[/admin/]",
        )

    def test_page_query_keeps_the_search_and_puts_the_page_last(self):
        request = RequestFactory().get("/admin/news/article/?search=cup&page=3")
        self.assertEqual(
            render("{% page_query 2 %}", request=request), "?search=cup&amp;page=2"
        )
        request = RequestFactory().get("/admin/news/article/")
        self.assertEqual(render("{% page_query 2 %}", request=request), "?page=2")

    def test_initials(self):
        user = factories.UserFactory.build(first_name="Odette", last_name="Marlowe")
        self.assertEqual(render("{{ user|initials }}", user=user), "OM")
        user = factories.UserFactory.build(first_name="", last_name="", username="zed")
        self.assertEqual(render("{{ user|initials }}", user=user), "ZE")


@per_shell(shells=("workbook",))
class TrailTests(TestCase):
    """Every page names the pages above it, each a link."""

    def setUp(self):
        super().setUp()
        self.superuser = factories.UserFactory.create(is_staff=True, is_superuser=True)

    def test_a_translation_names_its_article_and_the_tab_it_is_listed_in(self):
        article = ArticleFactory.create(headline="Flow Cup begins")
        translation = TranslationFactory.create(article=article, locale="fr")
        with self.login(self.superuser):
            self.get_check_200(
                "admin:news:article:translation:edit", article.pk, translation.locale
            )
        self.assertResponseContains(
            '<nav class="wb-trail" aria-label="You are here"><ol>'
            '<li><a href="/admin/"><span>Home</span></a></li>'
            '<li><a href="/admin/news/"><span>News</span></a></li>'
            '<li><a href="/admin/news/article/"><span>Articles</span></a></li>'
            '<li class="wb-trail-parent"><a href="/admin/news/article/%d/#translations-tab">'
            "%s<span>Flow Cup begins</span></a></li></ol></nav>"
            % (article.pk, ICON % "arrow-left"),
        )


@per_shell(shells=("workbook",))
class HomeTests(TestCase):
    def setUp(self):
        super().setUp()
        self.superuser = factories.UserFactory.create(
            is_staff=True, is_superuser=True, first_name="Odette"
        )

    def test_the_home_page_offers_each_components_jobs(self):
        with self.login(self.superuser):
            self.get_check_200("admin:index")
        self.assertResponseContains("<h1>Hello, Odette</h1>")
        self.assertResponseContains(
            '<a class="wb-task" href="%s"><span class="wb-task-icon">%s</span>'
            '<span class="wb-task-title">Write a news article</span>'
            '<span class="wb-task-note">Publish it now or later</span></a>'
            % (self.reverse("admin:news:article:add"), ICON % "newspaper"),
        )


@per_shell(shells=("workbook",))
class AddAnotherTests(TestCase):
    """Adding one after another: Save and add another comes back to the form."""

    def setUp(self):
        super().setUp()
        self.superuser = factories.UserFactory.create(is_staff=True, is_superuser=True)

    def test_an_add_form_offers_save_and_add_another(self):
        with self.login(self.superuser):
            self.get_check_200("admin:content:redirect:add")
        self.assertResponseContains(
            '<button type="submit" name="_addanother" value="1" class="wb-button">'
            "%sSave and add another redirect</button>" % (ICON % "copy-plus"),
        )

    def test_save_and_add_another_returns_to_the_add_form(self):
        data = {
            "source_url": "/old/",
            "destination_url": "/new/",
            "label": "Old fixtures",
            "active": "1",
            "permanent": "0",
            "_addanother": "1",
        }
        with self.login(self.superuser):
            self.post("admin:content:redirect:add", data=data)
        self.response_302()
        self.assertEqual(
            self.last_response["Location"], self.reverse("admin:content:redirect:add")
        )
        self.assertEqual(
            list(Redirect.objects.values_list("label", flat=True)), ["Old fixtures"]
        )

    def test_an_edit_form_has_no_save_and_add_another(self):
        redirect = Redirect.objects.create(source_url="/a/", destination_url="/b/")
        with self.login(self.superuser):
            self.get_check_200("admin:content:redirect:edit", redirect.pk)
        self.assertResponseNotContains(
            '<button type="submit" name="_addanother" value="1" class="wb-button">'
            "%sSave and add another redirect</button>" % (ICON % "copy-plus"),
        )


def checklist_html(kind, open_, optional):
    """
    A two-step checklist as ``_checklist.html`` draws it: the first step done,
    the second (optional or not) still to do.
    """
    if optional:
        score, total, percent, nxt = f"{ICON % 'circle-check'} All done", 1, 100, ""
        second, badge = "wb-step", '<span class="wb-step-optional">optional</span>'
    else:
        score, total, percent = "1 of 2 done", 2, 50
        nxt = '<span class="wb-checklist-next">Next: Set dates aside</span>'
        second, badge = "wb-step is-next", ""
    return (
        '<div class="wb-checklist-panel">'
        '<button type="button" class="wb-checklist-hide" data-wb-checklist-hide>'
        f'{ICON % "x"}<span aria-hidden="true">Hide</span>'
        '<span class="wb-sr">Hide the set-up checklists</span></button>'
        f'<details class="wb-sheet wb-checklist" data-wb-checklist="{kind}"'
        f'{" open" if open_ else ""}>'
        '<summary><h2 class="wb-checklist-title">Season set-up</h2>'
        '<span class="wb-checklist-toggle" aria-hidden="true">'
        f'{ICON % "chevron-down"}</span>'
        f'<span class="wb-checklist-score">{score}</span>{nxt}'
        '<span class="wb-progress" role="progressbar" aria-label="Season set-up" '
        f'aria-valuemin="0" aria-valuemax="{total}" aria-valuenow="1">'
        f'<span style="--done: {percent}%"></span></span></summary>'
        '<ol class="wb-steps"><li class="wb-step is-done">'
        f'<span class="wb-step-mark" aria-hidden="true">{ICON % "check"}</span>'
        '<span class="wb-step-body"><span class="wb-step-title">'
        '<a href="/one/">Name it</a></span><span class="wb-step-note">'
        '<span class="wb-sr">Done: </span>Named</span></span></li>'
        f'<li class="{second}"><span class="wb-step-mark" aria-hidden="true">2</span>'
        '<span class="wb-step-body"><span class="wb-step-title">'
        f'<a href="/two/">Set dates aside</a>{badge}</span>'
        '<span class="wb-step-note"><span class="wb-sr">To do: </span>Breaks'
        "</span></span></li></ol></details>"
        "<script>window.wbChecklist && "
        "wbChecklist(document.currentScript.parentNode)</script></div>"
    )


@per_shell(shells=("workbook",))
class ChecklistTests(TestCase):
    """
    The set-up checklist starts folded when every required step is done and
    open otherwise, worked out on the server so it works without scripts.
    """

    def render(self, kind, optional):
        steps = [
            Step("Name it", True, "Named", "/one/"),
            Step("Set dates aside", False, "Breaks", "/two/", optional=optional),
        ]
        return render_to_string(
            "touchtechnology/admin/workbook/_checklist.html",
            {
                "checklist": Setup("Season set-up", steps),
                "title": "Season set-up",
                "kind": kind,
            },
        )

    def test_a_checklist_with_a_step_to_do_starts_open(self):
        self.assertHTMLEqual(
            self.render("season", optional=False),
            checklist_html("season", open_=True, optional=False),
        )

    def test_a_checklist_with_only_optional_steps_left_starts_folded(self):
        self.assertHTMLEqual(
            self.render("division", optional=True),
            checklist_html("division", open_=False, optional=True),
        )
