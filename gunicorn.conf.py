"""Read automatically by gunicorn (Render's start command runs gunicorn directly).

Keeps the 512 MB server steady: image/OCR work fragments memory, so use fewer malloc
arenas and restart the worker between requests every few hundred requests.
"""
import ctypes

max_requests = 400
max_requests_jitter = 50

try:  # M_ARENA_MAX = -8; set in the master before workers fork, so they inherit it.
    ctypes.CDLL("libc.so.6").mallopt(-8, 2)
except (OSError, AttributeError):
    pass
