from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("letter/", views.letter_form, name="letter_form"),
    path("letter/handoff/", views.letter_handoff, name="letter_handoff"),
    path("letter/<str:case_encounter>/pdf/", views.letter_pdf, name="letter_pdf"),
    path("login/", auth_views.LoginView.as_view(template_name="letters/login.html",
                                                redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("settings/", views.settings_page, name="settings"),
    path("letters/", views.letter_list, name="letter_list"),
]
