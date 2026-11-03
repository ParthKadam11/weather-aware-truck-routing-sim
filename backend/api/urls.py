from django.urls import path

from api.views import AnalyzeRoutesView, HealthView, HeatmapView

urlpatterns = [
    path("health", HealthView.as_view(), name="health"),
    path("routes/analyze", AnalyzeRoutesView.as_view(), name="routes-analyze"),
    path("weather/heatmap", HeatmapView.as_view(), name="weather-heatmap"),
]
