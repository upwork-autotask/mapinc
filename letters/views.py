from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .docgen.service import LetterGenerationError, generate_letter
from .forms import AppSettingsForm, LetterForm
from .models import AppSettings, Letter

QUERY_FIELDS = ("case_encounter", "policy_id", "member_name", "dob", "admission", "folder_name", "user")
LETTER_FIELDS = ("case_encounter", "policy_id", "member_name", "dob", "admission", "folder_name")


def _parse_dob(value: str):
    try:
        return LetterForm.base_fields["dob"].to_python(value)
    except ValidationError:
        return value  # let the form report it on submit


def _initial_from_request(request) -> dict:
    """Existing letter (by case_encounter) first, then query-string values override field by field."""
    initial: dict = {}
    case_encounter = request.GET.get("case_encounter", "").strip()
    if case_encounter:
        existing = Letter.objects.filter(case_encounter=case_encounter).first()
        if existing:
            initial.update({name: getattr(existing, name) for name in LETTER_FIELDS})
    for name in QUERY_FIELDS:
        value = (request.GET.get(name) or "").strip()
        if value:
            initial[name] = _parse_dob(value) if name == "dob" else value
    return initial


@require_http_methods(["GET", "POST"])
def letter_form(request):
    context = {"app_settings": AppSettings.load()}
    if request.method == "POST":
        form = LetterForm(request.POST)
        if form.is_valid():
            try:
                letter = generate_letter(form.cleaned_data, form.cleaned_data.get("user", ""))
            except LetterGenerationError as exc:
                form.add_error(None, str(exc))
            else:
                return render(request, "letters/success.html", {**context, "letter": letter})
    else:
        form = LetterForm(initial=_initial_from_request(request))
    return render(request, "letters/form.html", {**context, "form": form})


def letter_pdf(request, case_encounter: str):
    letter = get_object_or_404(Letter, case_encounter=case_encounter)
    path = Path(letter.pdf_path) if letter.pdf_path else None
    if path is None or not path.is_file():
        raise Http404("PDF not found")
    return FileResponse(open(path, "rb"), content_type="application/pdf", filename=path.name)


SETTINGS_GROUPS = (
    ("Letter defaults", ("attn_default", "client_default", "doctor_default")),
    ("PDF output", ("pdf_root_folder", "pdf_filename_pattern")),
    ("Word template", ("template",)),
)


@login_required
@require_http_methods(["GET", "POST"])
def settings_page(request):
    app_settings = AppSettings.load()
    if request.method == "POST":
        form = AppSettingsForm(request.POST, request.FILES, instance=app_settings)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings saved.")
            return redirect("settings")
    else:
        form = AppSettingsForm(instance=app_settings)
    groups = [(title, [form[name] for name in names]) for title, names in SETTINGS_GROUPS]
    return render(request, "letters/settings.html",
                  {"form": form, "groups": groups, "app_settings": app_settings})


def admin_login_redirect(request):
    """Send the Django admin's login to the branded /login/ page, keeping ?next=."""
    return redirect(f"{reverse('login')}?next={request.GET.get('next', reverse('admin:index'))}")
