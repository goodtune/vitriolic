"""
Deleting a translation of an article, from the article's Translations tab.

Delete on the translation's row asks first, in a dialog. Confirming it must
delete the translation and return to the article's page, whose Translations tab
no longer lists it. ``test_admin_delete_modals`` reads the dialog of every
delete route but never confirms one; this test confirms this one, because the
view behind it once rendered the translation's permissions page instead of
deleting (#423).
"""

from urllib.parse import urljoin

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.admin_tabs import EMPTY_TAB, set_mode, show_tab
from tests.e2e.shells import ROW_MENU, by_shell, pane_id
from touchtechnology.news.tests.factories import ArticleFactory, TranslationFactory

MODES = [pytest.param(False, id="plain"), pytest.param(True, id="htmx")]

#: The row a list shows when it has nothing to list, and what it says.
EMPTY_ROW = by_shell(workbook="tr.wb-table-empty", explorer="td.empty-state")
EMPTY_ROW_TEXT = by_shell(
    workbook="No translations yet. Add the first translation",
    explorer="No translations yet. Add the first translation.",
)


@pytest.fixture
def article(db):
    """An article with one translation, in French."""
    article = ArticleFactory.create(headline="Eagles win the Spec Cup")
    TranslationFactory.create(
        article=article, locale="fr", headline="Les Aigles gagnent la Spec Cup"
    )
    return article


@pytest.mark.parametrize("htmx", MODES)
def test_deleting_a_translation_from_the_translations_tab(
    authenticated_page: Page, live_server, settings, screenshot_dir, article, htmx
):
    """
    Delete on the translation's row of the article's Translations tab asks
    first, then deletes that translation.

    Prerequisites:
    - An article with one translation, in French
    - A signed-in superuser

    Expected behaviour:
    - The dialog names the translation
    - Confirming deletes the translation and lands on the article's edit page
    - The Translations tab of that page says there are none ("No translations
      yet.", in the plural in both shells), and the translation's row is gone

    Runs traditionally (every tab in the page) and with
    ``TOUCHTECHNOLOGY_HTMX_ADMIN_TABS`` (the tab fetched when first shown).
    """
    set_mode(settings, htmx)
    page = authenticated_page
    translation = article.translations.get(locale="fr")
    edit_url = urljoin(live_server.url, str(article.urls["edit"]))

    page.goto(edit_url)
    pane = show_tab(page, pane_id("translations"))
    row = pane.locator("tbody tr", has_text=translation.headline)
    expect(row).to_have_count(1)
    row.get_by_role("button", name=ROW_MENU).click()
    row.get_by_role("button", name="Delete", exact=True).click()

    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    expect(dialog.get_by_role("heading")).to_have_text(
        by_shell(workbook=f"Delete {translation}?", explorer="Delete this translation?")
    )
    dialog.get_by_role(
        "button", name=by_shell(workbook="Delete translation", explorer="Delete")
    ).click()

    expect(page).to_have_url(edit_url)
    assert list(article.translations.all()) == []

    pane = show_tab(page, pane_id("translations"))
    expect(pane).not_to_contain_text(EMPTY_TAB)
    expect(pane.locator("tbody tr", has_text=translation.headline)).to_have_count(0)
    expect(pane.locator(EMPTY_ROW)).to_have_count(1)
    expect(pane.locator(EMPTY_ROW)).to_have_text(EMPTY_ROW_TEXT)
    mode = "htmx" if htmx else "plain"
    page.screenshot(path=screenshot_dir / f"delete_translation_{mode}.png")
