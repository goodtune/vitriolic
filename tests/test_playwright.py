def test_sitemap_xml(live_server, page):
    """
    Test that the sitemap.xml is accessible and returns a 200 status code.
    """
    response = page.goto(f"{live_server.url}/sitemap.xml")
    assert response.status == 200
    assert response.headers["content-type"] == "application/xml"
