"""
Views — HTTP handlers. Keep them thin: validate → call service → return JSON.

Django concept: a view receives a request and returns a response.
DRF's APIView gives us request.data (parsed JSON) and Response helpers.
"""

from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.providers.geocoding import GeocodingError
from api.providers.routing import RoutingError
from api.providers.weather import WeatherError
from api.serializers import AnalyzeRequestSerializer, HeatmapRequestSerializer
from api.services import analyze_routes, build_heatmap

logger = logging.getLogger(__name__)


class HealthView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})


class AnalyzeRoutesView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        ser = AnalyzeRequestSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        data = ser.validated_data
        try:
            result = analyze_routes(
                origin_query=data["origin"],
                destination_query=data["destination"],
                departure_iso=data["departure"],
                load_lb=data["load_lb"],
                interval_miles=data["interval_miles"],
                display_tz=data.get("display_tz"),
                demo_storm=data.get("demo_storm"),
            )
            return Response(result)
        except GeocodingError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except (RoutingError, WeatherError, ValueError) as exc:
            logger.exception("analyze failed")
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)


class HeatmapView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        ser = HeatmapRequestSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        data = ser.validated_data
        try:
            result = build_heatmap(
                origin_query=(data.get("origin") or None),
                destination_query=(data.get("destination") or None),
                geometries=data.get("geometries"),
                hours=data.get("hours", 48),
                load_lb=data.get("load_lb", 0),
                demo_storm=data.get("demo_storm"),
            )
            return Response(result)
        except GeocodingError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except (RoutingError, WeatherError, ValueError) as exc:
            logger.exception("heatmap failed")
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
