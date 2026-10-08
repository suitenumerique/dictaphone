"""URL configuration for the core app."""

from django.conf import settings
from django.urls import include, path, re_path

from lasuite.oidc_login.urls import urlpatterns as oidc_urls
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from core.api import (
    get_app_configuration,
    get_mobile_app_download_page,
    viewsets,
)
from core.api.audio_jobs import AudioJobViewSet
from core.authentication.views import PKCEOAuthTokenExchangeView

# - Main endpoints
router = DefaultRouter()
router.register("users", viewsets.UserViewSet, basename="users")
router.register("files", viewsets.FileViewSet, basename="files")
router.register("ai-jobs", viewsets.AiJobViewSet, basename="ai-jobs")

urlpatterns = [
    re_path(
        r"^audio-jobs/(?P<mode>transcoding|validation)/next$",
        AudioJobViewSet.as_view({"get": "next"}),
        name="audio-jobs-next",
    ),
    re_path(
        r"^audio-jobs/(?P<mode>transcoding|validation)/complete$",
        AudioJobViewSet.as_view({"post": "complete"}),
        name="audio-jobs-complete",
    ),
    path(
        f"api/{settings.API_VERSION}/",
        include(
            [
                *router.urls,
                *oidc_urls,
                path(
                    "oauth/token/",
                    PKCEOAuthTokenExchangeView.as_view(),
                    name="token_obtain_pair",
                ),
                path(
                    "oauth/token/refresh/",
                    TokenRefreshView.as_view(),
                    name="token_refresh",
                ),
                path("config/", get_app_configuration, name="config"),
                path(
                    "download-mobile-app/",
                    get_mobile_app_download_page,
                    name="download-mobile-app",
                ),
            ]
        ),
    ),
]
