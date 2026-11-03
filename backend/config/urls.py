"""
URLConf — maps URL paths to views (the HTTP entry points).

Django concept: urls.py is the router table. Each `path(...)` sends a
request to a view function/class. We mount the API under /api/.
"""

from django.urls import include, path

urlpatterns = [
    path("api/", include("api.urls")),
]
