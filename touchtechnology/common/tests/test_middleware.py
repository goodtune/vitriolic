from asgiref.sync import iscoroutinefunction
from django.http import HttpResponse
from django.test import RequestFactory
from test_plus import TestCase

from touchtechnology.common.middleware import DatastarMiddleware


class DatastarMiddlewareTests(TestCase):
    def setUp(self):
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
