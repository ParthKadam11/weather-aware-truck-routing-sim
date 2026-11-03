"""
DRF serializers — validate request JSON and shape responses.

Django/DRF concept: a serializer is like a Zod/Yup schema. It checks
incoming fields (types, ranges) before the view runs business logic.
We have no Django models, so these are plain Serializer classes (not ModelSerializer).
"""

from rest_framework import serializers

from core.checkpoints import ALLOWED_INTERVALS_MI


class AnalyzeRequestSerializer(serializers.Serializer):
    origin = serializers.CharField(max_length=256)
    destination = serializers.CharField(max_length=256)
    departure = serializers.CharField(
        help_text="ISO-8601 datetime. Naive values are treated as UTC."
    )
    load_lb = serializers.FloatField(min_value=0)
    interval_miles = serializers.IntegerField()
    display_tz = serializers.CharField(required=False, default="America/Chicago")
    demo_storm = serializers.BooleanField(required=False, allow_null=True, default=None)

    def validate_interval_miles(self, value: int) -> int:
        if value not in ALLOWED_INTERVALS_MI:
            raise serializers.ValidationError(
                f"Must be one of {list(ALLOWED_INTERVALS_MI)}"
            )
        return value


class HeatmapRequestSerializer(serializers.Serializer):
    origin = serializers.CharField(max_length=256)
    destination = serializers.CharField(max_length=256)
    hours = serializers.IntegerField(required=False, default=48, min_value=1, max_value=48)
    demo_storm = serializers.BooleanField(required=False, allow_null=True, default=None)
