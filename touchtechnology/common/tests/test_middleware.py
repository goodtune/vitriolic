import gzip

from asgiref.sync import iscoroutinefunction
from django.http import HttpResponse, StreamingHttpResponse
from django.test import RequestFactory
from test_plus import TestCase

from touchtechnology.common.middleware import DatastarMiddleware, GZipMiddleware

EVENTS = [b"data: one\n\n", b"data: two\n\n"]
PAGE = b"<p>" + b"ladder " * 100 + b"</p>"


class DatastarMiddlewareTests(TestCase):
    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()
        self.response = HttpResponse()

    def get_response(self, request):
        return self.response

    async def aget_response(self, request):
        return self.response

    def test_header_present(self):
        request = self.factory.get("/", headers={"Datastar-Request": "true"})
        response = DatastarMiddleware(self.get_response)(request)
        self.assertEqual(request.datastar, True)
        self.assertIs(response, self.response)

    def test_header_absent(self):
        request = self.factory.get("/")
        response = DatastarMiddleware(self.get_response)(request)
        self.assertEqual(request.datastar, False)
        self.assertIs(response, self.response)

    def test_header_with_another_value(self):
        request = self.factory.get("/", headers={"Datastar-Request": "false"})
        DatastarMiddleware(self.get_response)(request)
        self.assertEqual(request.datastar, False)

    def test_sync_get_response_is_not_a_coroutine(self):
        middleware = DatastarMiddleware(self.get_response)
        self.assertEqual(iscoroutinefunction(middleware), False)

    async def test_async_get_response(self):
        middleware = DatastarMiddleware(self.aget_response)
        self.assertEqual(iscoroutinefunction(middleware), True)
        request = self.factory.get("/", headers={"Datastar-Request": "true"})
        response = await middleware(request)
        self.assertEqual(request.datastar, True)
        self.assertIs(response, self.response)

    async def test_async_get_response_without_header(self):
        middleware = DatastarMiddleware(self.aget_response)
        request = self.factory.get("/")
        response = await middleware(request)
        self.assertEqual(request.datastar, False)
        self.assertIs(response, self.response)

    def test_marked_sync_and_async_capable(self):
        self.assertEqual(
            (DatastarMiddleware.sync_capable, DatastarMiddleware.async_capable),
            (True, True),
        )


class GZipMiddlewareTests(TestCase):
    """
    Django's GZipMiddleware compresses each chunk of an async stream as a gzip
    member of its own, and browsers decode only the first. An event stream
    goes out uncompressed; everything else is compressed as before.
    """

    def through_gzip(self, response):
        request = RequestFactory().get("/", headers={"Accept-Encoding": "gzip"})
        return GZipMiddleware(lambda request: response)(request)

    def test_async_event_stream_is_not_compressed(self):
        async def events():
            for event in EVENTS:
                yield event

        response = self.through_gzip(
            StreamingHttpResponse(
                events(), content_type="text/event-stream; charset=utf-8"
            )
        )
        self.assertEqual(response.get("Content-Encoding"), None)
        self.assertEqual(response.is_async, True)

    def test_sync_event_stream_is_not_compressed(self):
        response = self.through_gzip(
            StreamingHttpResponse(iter(EVENTS), content_type="text/event-stream")
        )
        self.assertEqual(response.get("Content-Encoding"), None)
        self.assertEqual(list(response.streaming_content), EVENTS)

    def test_another_stream_is_still_compressed(self):
        response = self.through_gzip(
            StreamingHttpResponse(iter(EVENTS), content_type="text/plain")
        )
        self.assertEqual(response["Content-Encoding"], "gzip")

    def test_page_is_still_compressed(self):
        response = self.through_gzip(HttpResponse(PAGE))
        self.assertEqual(response["Content-Encoding"], "gzip")
        self.assertEqual(gzip.decompress(response.content), PAGE)

    def test_subclass_extends_the_excluded_types(self):
        class Middleware(GZipMiddleware):
            excluded_content_types = (
                *GZipMiddleware.excluded_content_types,
                "text/html",
            )

        request = RequestFactory().get("/", headers={"Accept-Encoding": "gzip"})
        response = Middleware(lambda request: HttpResponse(PAGE))(request)
        self.assertEqual(response.get("Content-Encoding"), None)
        self.assertEqual(response.content, PAGE)
