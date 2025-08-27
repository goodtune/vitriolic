def test_sitemap_xml(live_server, page):
    """
    Test basic sitemap.xml accessibility and content type validation.

    This test provides fundamental validation that the XML sitemap endpoint
    is properly configured and accessible. It serves as a basic connectivity
    test for SEO functionality.

    Prerequisites:
    - Django sitemap framework configured
    - URL routing includes sitemap.xml endpoint
    - Web server properly serves XML content types

    Expected behavior:
    - /sitemap.xml URL returns HTTP 200 status
    - Response content-type header indicates XML format
    - Endpoint is accessible without authentication

    Args:
        live_server: Django live server fixture
        page: Playwright page fixture
    """
    response = page.goto(f"{live_server.url}/sitemap.xml")
    assert response.status == 200
    assert response.headers["content-type"] == "application/xml"
