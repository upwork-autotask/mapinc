from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from letters.views import admin_login_redirect

urlpatterns = [
    path("admin/login/", admin_login_redirect),
    path("admin/", admin.site.urls),
    path("", include("letters.urls")),
    path("", RedirectView.as_view(pattern_name="letter_form", permanent=False)),
]
