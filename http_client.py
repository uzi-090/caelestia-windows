"""Small verified-HTTPS client using Windows' normal TLS trust store."""
from __future__ import annotations

import ctypes
import json
import os
import urllib.error
import urllib.parse
import urllib.request


class HttpStatusError(OSError):
    def __init__(self, status: int):
        self.status = status
        super().__init__(f'Service returned HTTP {status}')


def fetch_json(url: str, *, max_bytes: int = 2 * 1024 * 1024,
               user_agent: str = 'CaelestiaWindows/1.0'):
    return json.loads(fetch_bytes(url, max_bytes=max_bytes, user_agent=user_agent))


def fetch_bytes(url: str, *, max_bytes: int = 2 * 1024 * 1024,
                accept: str = 'application/json',
                user_agent: str = 'CaelestiaWindows/1.0') -> bytes:
    if max_bytes < 1:
        raise ValueError('Service response size must be positive')
    if '\r' in accept or '\n' in accept:
        raise ValueError('Invalid service content type')
    if not user_agent or '\r' in user_agent or '\n' in user_agent:
        raise ValueError('Invalid service user agent')
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname:
        raise ValueError('Service requests require HTTPS')
    if os.name != 'nt':
        request = urllib.request.Request(url, headers={'User-Agent': user_agent, 'Accept': accept})
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                raw = response.read(max_bytes + 1)
                if len(raw) > max_bytes:
                    raise ValueError('Service response exceeded expected size')
                return raw
        except urllib.error.HTTPError as error:
            raise HttpStatusError(error.code) from error
    from ctypes import wintypes as wt
    api = ctypes.WinDLL('winhttp.dll', use_last_error=True)
    handle = wt.HANDLE
    api.WinHttpOpen.argtypes = [wt.LPCWSTR, wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD]
    api.WinHttpOpen.restype = handle
    api.WinHttpConnect.argtypes = [handle, wt.LPCWSTR, wt.WORD, wt.DWORD]
    api.WinHttpConnect.restype = handle
    api.WinHttpOpenRequest.argtypes = [handle, wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR, ctypes.c_void_p, wt.DWORD]
    api.WinHttpOpenRequest.restype = handle
    api.WinHttpSetTimeouts.argtypes = [handle, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    api.WinHttpSendRequest.argtypes = [handle, wt.LPCWSTR, wt.DWORD, ctypes.c_void_p, wt.DWORD, wt.DWORD, ctypes.c_size_t]
    api.WinHttpReceiveResponse.argtypes = [handle, ctypes.c_void_p]
    api.WinHttpQueryHeaders.argtypes = [handle, wt.DWORD, wt.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(wt.DWORD), ctypes.POINTER(wt.DWORD)]
    api.WinHttpQueryDataAvailable.argtypes = [handle, ctypes.POINTER(wt.DWORD)]
    api.WinHttpReadData.argtypes = [handle, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD)]
    api.WinHttpCloseHandle.argtypes = [handle]
    opened = []

    def require(value):
        if not value:
            code = ctypes.get_last_error()
            raise OSError(code, f'Windows service connection failed ({code})')
        return value

    try:
        session = require(api.WinHttpOpen(user_agent, 4, None, None, 0))
        opened.append(session)
        require(api.WinHttpSetTimeouts(session, 3000, 5000, 5000, 12000))
        connection = require(api.WinHttpConnect(session, parsed.hostname, parsed.port or 443, 0))
        opened.append(connection)
        resource = parsed.path or '/'
        if parsed.query:
            resource += '?' + parsed.query
        request = require(api.WinHttpOpenRequest(connection, 'GET', resource, None, None, None, 0x00800000))
        opened.append(request)
        require(api.WinHttpSendRequest(request, f'Accept: {accept}\r\n', 0xFFFFFFFF, None, 0, 0, 0))
        require(api.WinHttpReceiveResponse(request, None))
        status = wt.DWORD()
        length = wt.DWORD(ctypes.sizeof(status))
        require(api.WinHttpQueryHeaders(request, 19 | 0x20000000, None, ctypes.byref(status), ctypes.byref(length), None))
        if status.value != 200:
            raise HttpStatusError(status.value)
        raw = bytearray()
        while True:
            available = wt.DWORD()
            require(api.WinHttpQueryDataAvailable(request, ctypes.byref(available)))
            if not available.value:
                break
            size = min(available.value, 65536)
            buffer = ctypes.create_string_buffer(size)
            received = wt.DWORD()
            require(api.WinHttpReadData(request, buffer, size, ctypes.byref(received)))
            if not received.value:
                break
            raw.extend(buffer.raw[:received.value])
            if len(raw) > max_bytes:
                raise ValueError('Service response exceeded expected size')
        return bytes(raw)
    finally:
        for item in reversed(opened):
            api.WinHttpCloseHandle(item)
