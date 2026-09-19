from django.urls import path

from . import views

urlpatterns = [
    path("letter/", views.letter_form, name="letter_form"),
    path("letter/<str:case_encounter>/pdf/", views.letter_pdf, name="letter_pdf"),
]
