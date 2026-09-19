import json
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .docgen.service import LetterGenerationError, generate_letter
from .forms import AppSettingsForm, LetterForm
from .models import AppSettings, Handoff, Letter

QUERY_FIELDS = ("case_encounter", "policy_id", "member_name", "dob", "admission", "folder_name", "user")
LETTER_FIELDS = ("case_encounter", "policy_id", "member_name", "dob", "admission", "folder_name")


def _parse_dob(value: str):
    try:
        return LetterForm.base_fields["dob"].to_python(value)
    except ValidationError:
        return value  # let the form report it on submit


def _initial_from_request(request) -> tuple[dict, bool]:
    """
    Prefill order: existing letter (by case_encounter), then values stashed by a
    handoff token (?t=), then explicit query-string values, each overriding the
    last field by field. Returns (initial, token_expired).
    """
    params: dict = {}
    expired = False
    token = request.GET.get("t", "").strip()
    if token:
        stashed = Handoff.take(token)
        expired = stashed is None
        params.update(stashed or {})
    params.update({name: request.GET[name] for name in QUERY_FIELDS if name in request.GET})

    initial: dict = {}
    case_encounter = (params.get("case_encounter") or "").strip()
    if case_encounter:
        existing = Letter.objects.filter(case_encounter=case_encounter).first()
        if existing:
            initial.update({name: getattr(existing, name) for name in LETTER_FIELDS})
    for name in QUERY_FIELDS:
        value = (params.get(name) or "").strip()
        if value:
            initial[name] = _parse_dob(value) if name == "dob" else value
    return initial, expired


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
        initial, expired = _initial_from_request(request)
        form = LetterForm(initial=initial)
        context["token_expired"] = expired
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


LIST_PAGE_SIZE = 25


@login_required
def letter_list(request):
    """History of generated letters, newest change first, with a simple search box."""
    q = request.GET.get("q", "").strip()
    letters = Letter.objects.all()
    if q:
        letters = letters.filter(
            Q(case_encounter__icontains=q) | Q(policy_id__icontains=q) | Q(member_name__icontains=q))
    page = Paginator(letters, LIST_PAGE_SIZE).get_page(request.GET.get("page"))
    return render(request, "letters/list.html", {"page": page, "q": q, "total": page.paginator.count})


@csrf_exempt
@require_http_methods(["POST"])
def letter_handoff(request):
    """
    Called by the Access/Outlook launcher: stash the field values and answer
    with the URL to open (plain text), so the browser URL carries only a token.
    Accepts form-encoded or JSON bodies with the query-string field names.
    """
    if request.content_type == "application/json":
        try:
            payload = json.loads(request.body or b"{}")
        except ValueError:
            return HttpResponseBadRequest("invalid JSON")
    else:
        payload = request.POST
    data = {name: str(payload.get(name) or "").strip() for name in QUERY_FIELDS}
    token = Handoff.create(data)
    url = request.build_absolute_uri(f"{reverse('letter_form')}?t={token}")
    return HttpResponse(url, content_type="text/plain; charset=utf-8")
