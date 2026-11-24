import os
import socket


def site(request):
    """
    The host name the admin footer shows.

    The harness sets ``VITRIOLIC_DEMO_HOSTNAME`` to an invented name so that
    screenshots made for a public record never carry the machine's own name;
    without it the demo project behaves like the library and shows the real
    one.
    """
    return {
        "hostname": os.environ.get("VITRIOLIC_DEMO_HOSTNAME") or socket.gethostname()
    }
