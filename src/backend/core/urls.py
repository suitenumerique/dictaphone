"""URL configuration for the core app."""

from django.conf import settings
from django.urls import include, path

from lasuite.oidc_login.urls import urlpatterns as oidc_urls
from rest_framework.routers import DefaultRouter

from core.api import get_frontend_configuration, get_mobile_redirect, viewsets

# - Main endpoints
router = DefaultRouter()
router.register("users", viewsets.UserViewSet, basename="users")
router.register("files", viewsets.FileViewSet, basename="files")
router.register("ai-jobs", viewsets.AiJobViewSet, basename="ai-jobs")


urlpatterns = [
    path(
        f"api/{settings.API_VERSION}/",
        include(
            [
                *router.urls,
                *oidc_urls,
                path("config/", get_frontend_configuration, name="config"),
                path("mobile-redirect/", get_mobile_redirect, name="mobile-redirect"),
            ]
        ),
    ),
]
