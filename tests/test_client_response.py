# -*- coding: utf-8 -*-
"""Tests for aiohttp/client.py"""

import asyncio
import gc
from unittest import mock

import pytest
from yarl import URL

import aiohttp
from aiohttp import helpers
from aiohttp.client_reqrep import ClientResponse


def test_del():
    loop = mock.Mock()
    response = ClientResponse('get', URL('http://del-cl-resp.org'))
    response._post_init(loop)
    loop.get_debug = mock.Mock()
    loop.get_debug.return_value = True

    connection = mock.Mock()
    response._closed = False
    response._connection = connection
    loop.set_exception_handler(lambda loop, ctx: None)

    with pytest.warns(ResourceWarning):
        del response
        gc.collect()

    connection.release.assert_called_with()


def test_close(loop):
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response._post_init(loop)
    response._closed = False
    response._connection = mock.Mock()
    response.close()
    assert response.connection is None
    response.close()
    response.close()


def test_wait_for_100_1(loop):
    response = ClientResponse(
        'get', URL('http://python.org'), continue100=object())
    response._post_init(loop)
    assert response._continue is not None
    response.close()


def test_wait_for_100_2(loop):
    response = ClientResponse(
        'get', URL('http://python.org'))
    response._post_init(loop)
    assert response._continue is None
    response.close()


def test_repr(loop):
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response._post_init(loop)
    response.status = 200
    response.reason = 'Ok'
    assert '<ClientResponse(http://def-cl-resp.org) [200 Ok]>'\
        in repr(response)


def test_repr_non_ascii_url():
    response = ClientResponse('get', URL('http://fake-host.org/\u03bb'))
    assert "<ClientResponse(http://fake-host.org/%CE%BB) [None None]>"\
        in repr(response)


def test_repr_non_ascii_reason():
    response = ClientResponse('get', URL('http://fake-host.org/path'))
    response.reason = '\u03bb'
    assert "<ClientResponse(http://fake-host.org/path) [None \\u03bb]>"\
        in repr(response)


def test_url_obj_deprecated():
    response = ClientResponse('get', URL('http://fake-host.org/'))
    with pytest.warns(DeprecationWarning):
        response.url_obj


@asyncio.coroutine
def test_read_and_release_connection(loop):
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response._post_init(loop)

    def side_effect(*args, **kwargs):
        fut = helpers.create_future(loop)
        fut.set_result(b'payload')
        return fut
    content = response.content = mock.Mock()
    content.read.side_effect = side_effect

    res = yield from response.read()
    assert res == b'payload'
    assert response._connection is None


@asyncio.coroutine
def test_read_and_release_connection_with_error(loop):
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response._post_init(loop)
    content = response.content = mock.Mock()
    content.read.return_value = helpers.create_future(loop)
    content.read.return_value.set_exception(ValueError)

    with pytest.raises(ValueError):
        yield from response.read()
    assert response._closed


@asyncio.coroutine
def test_release(loop):
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response._post_init(loop)
    fut = helpers.create_future(loop)
    fut.set_result(b'')
    content = response.content = mock.Mock()
    content.readany.return_value = fut

    response.release()
    assert response._connection is None


@asyncio.coroutine
def test_release_on_del(loop):
    connection = mock.Mock()
    connection.protocol.upgraded = False

    def run(conn):
        response = ClientResponse('get', URL('http://def-cl-resp.org'))
        response._post_init(loop)
        response._closed = False
        response._connection = conn

    run(connection)

    assert connection.release.called


@asyncio.coroutine
def test_response_eof(loop):
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response._post_init(loop)
    response._closed = False
    conn = response._connection = mock.Mock()
    conn.protocol.upgraded = False

    response._response_eof()
    assert conn.release.called
    assert response._connection is None


@asyncio.coroutine
def test_response_eof_upgraded(loop):
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response._post_init(loop)

    conn = response._connection = mock.Mock()
    conn.protocol.upgraded = True

    response._response_eof()
    assert not conn.release.called
    assert response._connection is conn


@asyncio.coroutine
def test_text(loop):
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response._post_init(loop)

    def side_effect(*args, **kwargs):
        fut = helpers.create_future(loop)
        fut.set_result('{"тест": "пройден"}'.encode('cp1251'))
        return fut

    response.headers = {
        'Content-Type': 'application/json;charset=cp1251'}
    content = response.content = mock.Mock()
    content.read.side_effect = side_effect

    res = yield from response.text()
    assert res == '{"тест": "пройден"}'
    assert response._connection is None


@asyncio.coroutine
def test_text_bad_encoding(loop):
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response._post_init(loop)

    def side_effect(*args, **kwargs):
        fut = helpers.create_future(loop)
        fut.set_result('{"тестkey": "пройденvalue"}'.encode('cp1251'))
        return fut

    # lie about the encoding
    response.headers = {
        'Content-Type': 'application/json;charset=utf-8'}
    content = response.content = mock.Mock()
    content.read.side_effect = side_effect
    with pytest.raises(UnicodeDecodeError):
        yield from response.text()
    # only the valid utf-8 characters will be returned
    res = yield from response.text(errors='ignore')
    assert res == '{"key": "value"}'
    assert response._connection is None


@asyncio.coroutine
def test_text_custom_encoding(loop):
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response._post_init(loop)

    def side_effect(*args, **kwargs):
        fut = helpers.create_future(loop)
        fut.set_result('{"тест": "пройден"}'.encode('cp1251'))
        return fut

    response.headers = {
        'Content-Type': 'application/json'}
    content = response.content = mock.Mock()
    content.read.side_effect = side_effect
    response._get_encoding = mock.Mock()

    res = yield from response.text(encoding='cp1251')
    assert res == '{"тест": "пройден"}'
    assert response._connection is None
    assert not response._get_encoding.called


@asyncio.coroutine
def test_text_detect_encoding(loop):
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response._post_init(loop)

    def side_effect(*args, **kwargs):
        fut = helpers.create_future(loop)
        fut.set_result('{"тест": "пройден"}'.encode('cp1251'))
        return fut

    response.headers = {'Content-Type': 'text/plain'}
    content = response.content = mock.Mock()
    content.read.side_effect = side_effect

    yield from response.read()
    res = yield from response.text()
    assert res == '{"тест": "пройден"}'
    assert response._connection is None


@asyncio.coroutine
def test_text_after_read(loop):
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response._post_init(loop)

    def side_effect(*args, **kwargs):
        fut = helpers.create_future(loop)
        fut.set_result('{"тест": "пройден"}'.encode('cp1251'))
        return fut

    response.headers = {
        'Content-Type': 'application/json;charset=cp1251'}
    content = response.content = mock.Mock()
    content.read.side_effect = side_effect

    res = yield from response.text()
    assert res == '{"тест": "пройден"}'
    assert response._connection is None


@asyncio.coroutine
def test_json(loop):
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response._post_init(loop)

    def side_effect(*args, **kwargs):
        fut = helpers.create_future(loop)
        fut.set_result('{"тест": "пройден"}'.encode('cp1251'))
        return fut

    response.headers = {
        'Content-Type': 'application/json;charset=cp1251'}
    content = response.content = mock.Mock()
    content.read.side_effect = side_effect

    res = yield from response.json()
    assert res == {'тест': 'пройден'}
    assert response._connection is None


@asyncio.coroutine
def test_json_custom_loader(loop):
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response._post_init(loop)
    response.headers = {
        'Content-Type': 'application/json;charset=cp1251'}
    response._content = b'data'

    def custom(content):
        return content + '-custom'

    res = yield from response.json(loads=custom)
    assert res == 'data-custom'


@asyncio.coroutine
def test_json_no_content(loop):
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response._post_init(loop)
    response.headers = {
        'Content-Type': 'data/octet-stream'}
    response._content = b''

    with pytest.raises(aiohttp.ClientResponseError):
        yield from response.json()

    res = yield from response.json(content_type=None)
    assert res is None


@asyncio.coroutine
def test_json_override_encoding(loop):
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response._post_init(loop)

    def side_effect(*args, **kwargs):
        fut = helpers.create_future(loop)
        fut.set_result('{"тест": "пройден"}'.encode('cp1251'))
        return fut

    response.headers = {
        'Content-Type': 'application/json;charset=utf8'}
    content = response.content = mock.Mock()
    content.read.side_effect = side_effect
    response._get_encoding = mock.Mock()

    res = yield from response.json(encoding='cp1251')
    assert res == {'тест': 'пройден'}
    assert response._connection is None
    assert not response._get_encoding.called


@pytest.mark.xfail
def test_override_flow_control(loop):
    class MyResponse(ClientResponse):
        flow_control_class = aiohttp.StreamReader
    response = MyResponse('get', URL('http://my-cl-resp.org'))
    response._post_init(loop)
    response._connection = mock.Mock()
    assert isinstance(response.content, aiohttp.StreamReader)
    response.close()


def test_get_encoding_unknown(loop):
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response._post_init(loop)

    response.headers = {'Content-Type': 'application/json'}
    with mock.patch('aiohttp.client_reqrep.chardet') as m_chardet:
        m_chardet.detect.return_value = {'encoding': None}
        assert response._get_encoding() == 'utf-8'


def test_raise_for_status_2xx():
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response.status = 200
    response.reason = 'OK'
    response.raise_for_status()  # should not raise


def test_raise_for_status_4xx():
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response.status = 409
    response.reason = 'CONFLICT'
    with pytest.raises(aiohttp.ClientResponseError) as cm:
        response.raise_for_status()
    assert str(cm.value.code) == '409'
    assert str(cm.value.message) == "CONFLICT"


def test_resp_host():
    response = ClientResponse('get', URL('http://del-cl-resp.org'))
    assert 'del-cl-resp.org' == response.host


def test_content_type():
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response.headers = {'Content-Type': 'application/json;charset=cp1251'}

    assert 'application/json' == response.content_type


def test_content_type_no_header():
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response.headers = {}

    assert 'application/octet-stream' == response.content_type


def test_charset():
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response.headers = {'Content-Type': 'application/json;charset=cp1251'}

    assert 'cp1251' == response.charset


def test_charset_no_header():
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response.headers = {}

    assert response.charset is None


def test_charset_no_charset():
    response = ClientResponse('get', URL('http://def-cl-resp.org'))
    response.headers = {'Content-Type': 'application/json'}

    assert response.charset is None
